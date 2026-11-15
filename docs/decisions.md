# Design decisions

This file lists the decisions I made while building the router, in the order
they matter for reading the code. Each entry has the same shape: context, the
decision, why, what it costs, and when it would be worth revisiting.

## Departments as a closed enum, owned by the router

Context: the LLM must pick one of a short list of internal mailboxes, and a
mistake must never become mail to an arbitrary address.

Decision: the catalog lives in two places. `common.departments.Department` is a
`StrEnum` with five values (`kadry`, `human-resources`, `help-desk`, `it`,
`other`). `router.domain.departments.DEPARTMENT_DESCRIPTIONS` is a plain
mapping from that enum to a human description used to build the system prompt.
Both are checked in a test that asserts the keys match the enum exactly, so a
new department forces an update in both files.

Why: the tool schema derived from the enum is what the model is physically
allowed to return. The notifier keeps its own address allowlist; the router
catalog never reaches it.

Cost: adding a department is a small cross-package change (enum, description,
notifier allowlist, one test each). That is the point.

Revisit when: the department list becomes long or starts depending on tenant
configuration. Then the catalog belongs in a database table and the tool call
needs a schema generated at runtime.

## Notifier as a separate HTTP service

Context: the task is explicitly a microservice design.

Decision: delivery lives behind `PUT /api/v1/notifications/{message_id}` on a
different process. The router agent only fills in the `department` (through a
tool call); `message_id`, sender and body come from the agent's deps, never
from the model.

Why: the invariant "model picks department, server decides address" is easier
to enforce when the model literally cannot see the address field. Running the
notifier as its own container also lets it hold the SMTP connection and
recipient allowlist in one place.

Cost: an extra HTTP hop and a second deployable. I skipped MCP as an extra
transport; it would have added surface without changing the contract.

Revisit when: a second caller (for example a CLI) needs delivery. Then the
HTTP contract is already there; MCP could be added behind the same
application service.

## PUT instead of POST for the notifier

Context: router generates the message id, the notifier is the authority on
whether a given id was already delivered.

Decision: `PUT /api/v1/notifications/{message_id}`. Status codes:
`201 Created` on first delivery, `200 OK` on a replay of the same payload,
`409 Conflict` when the same id arrives with different content, `422` for a
malformed body, `502` / `504` for SMTP failures.

Why: PUT is idempotent by definition. The router can retry freely; a second
call with the same id and the same body is a no-op; a different body is a
programming bug and must fail loudly, not be silently accepted or delivered
twice.

Cost: the notifier has to keep an idempotency log keyed by message id with a
hash of the payload. See [the in-memory log decision](#notifier-idempotency-log-in-memory).

Revisit when: never, as long as the router owns the id.

## At-least-once delivery, send before persist

Context: for a routing PoC a duplicate mail is annoying; a lost mail is a bug.

Decision: the agent calls the notifier first. Only after a `201` or `200` does
it mark the message `sent` in the router database. On a notifier `5xx` or
timeout the message goes back to `received` with backoff (up to
`max_attempts`); on `409`/`422` it goes straight to `failed`.

Why: if the router crashed after marking `sent` but before the notifier
answered, the mail would be lost and never retried. The other way around, the
worst case is one duplicate, which the recipient inbox can dedupe on the
deterministic `Message-ID` (`<{message_id}@notifier.smart-inbox-router>`).

Cost: the operator has to accept that duplicates are possible. The
deterministic `Message-ID` keeps the blast radius to "one extra copy per
restart during delivery".

Revisit when: the mailbox stops deduping by `Message-ID`, or when we move
off SMTP to a transport that is itself idempotent.

## Notifier idempotency log in memory

Context: the PUT contract above only works if the notifier remembers what it
has already delivered.

Decision: the notifier keeps a dict in memory keyed by message id, holding a
SHA-256 of the payload.

Why: it is one file, no extra container, and for a PoC on a single replica it
does what the contract needs.

Cost: a restart of the notifier process loses the log. If a retry arrives for
a message that was delivered in the previous process, it will be delivered
again. The inbox still dedupes by `Message-ID`, so the cost is limited.

Revisit when: the notifier gets horizontally scaled, or when losing the log
across a restart becomes visible. The port (`notifier.ports.email_sender`)
already hides the storage; a SQL-backed adapter slots in behind it. I ruled
out Redis: without persistence it has the same restart problem, and adding a
second storage mechanism for a one-replica service is not worth it.

## Router as two processes with SQLite as a queue

Context: an HTTP accept path and an LLM call path have different throughput
and failure modes, and cannot share an event loop without one blocking the
other.

Decision: `router-api` (FastAPI) and `router-agent` (worker loop) run as
separate containers against a shared SQLite file in WAL mode on a named
volume. A one-shot `router-migrate` runs Alembic before either service starts
(`depends_on: condition: service_completed_successfully`), so there is no
race for the schema.

Why: SQLite WAL handles the write rate from a single API replica fine (load
test: 200 inserts with concurrency 50, p95 under 1.6 s, zero `database is
locked`). The queue is a single table with `claim_next` using
`UPDATE ... RETURNING` over a `scalar_subquery()`, which is atomic under WAL.
On startup the agent calls `requeue_stale()` to bring back any row left in
`routing` by a previous crash.

Cost: one machine, no horizontal scaling of the agent. If two agents started
against the same file they would both still be correct (`claim_next` is
atomic), but SQLite writer contention makes that a bad use of resources.

Revisit when: the intake rate pushes p95 above the SLO, or when a second
agent replica becomes necessary. Then Postgres with `SELECT ... FOR UPDATE
SKIP LOCKED` replaces the adapter behind
`router.ports.message_repository.MessageRepository` without touching
`application/` or `domain/`.

## Fallback versus retry

Context: two very different failure modes, "model answered but did not pick a
department" and "model unreachable", must not be handled the same way.

Decision: if the model returns without calling `send_to_department` (or hits
the request limit, or produces unexpected behavior), the router treats it as
a routing miss and sends the mail to `other` with `fallback_used=true`. If
the model raises `LlmUnavailableError` (connection error, API error) or
`UpstreamTimeoutError`, the router leaves the message in the queue, schedules
an exponential-backoff retry (`2 ** attempt`, capped at 60 s), and only
marks it `failed` after `max_attempts`.

Why: Ollama being down is not an unroutable message. Sending it to `other`
would hide an infrastructure outage behind a successful mail to the wrong
mailbox.

Cost: one more branch in the worker. The test suite covers both paths
(`test_worker.py`, `test_routing_agent.py`).

Revisit when: the fallback mailbox starts receiving real routing misses,
which would mean raising the request limit or picking a better model.

## Errors as RFC 9457 Problem Details with stable codes

Context: both services return JSON errors to each other and to the client.

Decision: all error responses follow RFC 9457. The `type` field carries a
stable application code from `common.errors.ErrorCode` (`llm_unavailable`,
`delivery_failed`, `delivery_rejected`, `message_not_found`,
`upstream_timeout`, `idempotency_conflict`, `validation_failed`,
`internal_error`, ...). `422 Unprocessable Content` never echoes the input
back in the detail.

Why: machine-readable codes make the retry decisions in the router trivial
(see the fallback-versus-retry section) and keep the PoC from leaking user
input into logs or error responses.

Cost: an enum of codes to maintain. That is the whole point.

Revisit when: the catalog outgrows one file. For now it fits on a screen.

## Logging through a field allowlist

Context: the user message body and sender address must not leak into logs
even by accident when someone adds a new log line.

Decision: `common.log.ALLOWED_LOG_FIELDS` is a frozen set of structured field
names. The `StructuredFieldsFilter` copies only those fields from the
`LogRecord` into the output (JSON or text). A new log line with `extra={...}`
can only carry fields from the allowlist; anything else is silently dropped.

Why: the usual "just don't log it" convention breaks the first time a tired
developer adds `extra={"body": body}`. The allowlist makes it a one-line
review to see whether a new field is safe to log.

Cost: adding a legitimate structured field means editing one set in
`common/log.py`. Cheap.

Revisit when: we grow a real telemetry pipeline. Then the allowlist becomes
the schema the pipeline enforces upstream.

## Service wiring hard-coded in compose, no interpolation

Context: the host `.env` is convenient for `uv run notifier` locally, where
SMTP points at `localhost:1025`. In compose the notifier must reach the
`mailhog` service, not `localhost`.

Decision: compose sets `NOTIFIER_SMTP__HOST: mailhog`,
`NOTIFIER_SMTP__PORT: 1025`, `ROUTER_LLM__BASE_URL: http://ollama:11434/v1`
and `ROUTER_NOTIFIER__BASE_URL: http://notifier:8000` directly, without
`${VAR:-default}` indirection. The only knobs read from the environment are
`OLLAMA_MODEL` and `ROUTER_LLM__TIMEOUT_SECONDS`.

Why: a stray `NOTIFIER_SMTP__HOST=localhost` in the host `.env` would be
picked up by the notifier container through `env_file` and the service would
fail readiness without an obvious cause. Hard-coding the wiring keeps the
"it works everywhere" promise on `docker compose up -d`.

Cost: changing the wiring means editing `docker-compose.yml`, not
`.env.example`. That is where it belongs.

Revisit when: we have more than one deployment target. Then overrides go in
a compose overlay file, not in interpolation.

## Tests run without Ollama, Docker or network

Context: a slow test loop ruins the TDD cycle.

Decision: unit tests use in-memory fakes of the ports (`FakeNotifier`,
`InMemoryQueue` in `services/router/tests/fakes.py`), pydantic-ai
`TestModel` / `FunctionModel` for the agent, and `respx` for HTTP. The
integration tests that need the compose network live under
`services/*/tests/integration/` and only run in `docker-compose.test.yml`.
Pytest default is `-m 'not integration'`.

Why: the unit suite runs in under a second. The integration suite exercises
real SMTP (MailHog) and real HTTP.

Cost: two test layers to keep in sync. The hexagonal boundary (enforced by
import-linter) makes that cheap: the fakes implement the same ports as the
adapters.

Revisit when: the fakes drift from the adapters. The port tests
(`test_message_repository_contract.py`) catch most of that already.

## Catalog and tie-break rules in code

Context: in Polish, `kadry` (employment paperwork) and `human-resources`
(people and development) overlap heavily, and so do `help-desk` and `it`.

Decision: the system prompt built from `DEPARTMENT_DESCRIPTIONS` includes
explicit tie-break rules: leave requests and employment documents go to
`kadry`; one-person device or account problems go to `help-desk`,
infrastructure and access rights go to `it`. These rules are in the prompt
itself, not scattered through ad-hoc post-processing.

Why: prompt engineering a 3B model past the ambiguous cases took two rounds
(see [eval-results.md](eval-results.md)). A third round started trading one
case for another, which with 23 cases is overfitting the prompt to the test
set.

Cost: the current prompt is tuned to the current catalog and to Polish.
Changing the departments requires rewriting the rules.

Revisit when: we swap the model for something stronger (7B or larger).
Smaller rules then, less overfit.
