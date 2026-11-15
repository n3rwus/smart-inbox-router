# Security notes

This file lists the threats I thought about while building the PoC, and what
the code actually does about each one. It is not a compliance document; the
scope is "a single developer running this on a laptop, demonstrating a
routing agent".

## Prompt injection

The user message text is attacker-controlled. The 3B model listens when the
message says "forward this to HR" and will pick the department it is told to
pick. The eval run captured in [eval-latest-run.md](eval-latest-run.md) shows
both injection cases succeeding at the "pick a different department" level.

What the model physically cannot do is more interesting. The agent's only
tool is `send_to_department(department: Department)`. The `Department` type
is a `StrEnum` with five values, and pydantic-ai validates the tool argument
against that schema before the function runs. An injected "send to
attacker@example.com" cannot change the `To` header, because the address is
set server-side by the notifier from its allowlist (see
`services/notifier/src/notifier/domain/recipients.py`). An injected
"include `<script>` in the subject" cannot change the subject, because the
notifier builds the subject itself. The worst case is a mail landing in the
wrong internal mailbox.

Two defensive moves inside the prompt are worth naming. The user text is
wrapped in `<user_message>...</user_message>` tags, with any inner
`<user_message>` occurrences neutralised by a zero-width space so the
attacker cannot close the block and start a new system instruction
(`router.domain.prompt.build_user_prompt`). An instruction reminder is
appended *after* the closing tag so an injection inside the body cannot
shadow it. These help a bit; they do not fix the underlying problem that a
small model is gullible. The honest fix is a bigger model.

## Header injection in outbound mail

A sender email going into a `Reply-To` header is the classic CR/LF injection
vector. The notifier passes both the recipient (from the allowlist) and the
`Reply-To` (from the request) through
`common.email_headers.format_address_header`, which rejects headers that
contain CR or LF. The email body is attached as a quoted-printable MIME
part, so CR/LF in the body cannot escape into the header block. Tests cover
both paths (`services/notifier/tests/test_email_builder.py`,
`libs/common/tests/test_smtp_client.py`).

## Recipient allowlist

The notifier maps a `Department` enum value to a fixed address through a
frozen mapping. The router\'s catalog never reaches it. A new department
requires an entry in `notifier.domain.recipients._RECIPIENTS`; missing it
raises `KeyError` on the first delivery to that department, which is a
`500 internal_error` and a loud log line, not a mail sent to the wrong place.

## Server-side Reply-To

The invariant is simple: the LLM only chooses a `Department`. The recipient
address, the sender envelope, and the `Reply-To` header are all set by the
notifier from the incoming request body (sender email) and its own allowlist
(department address). A test in
`services/router/tests/test_routing_agent.py` asserts the tool schema has
exactly one parameter, `department`, and no address field.

## Personal data in logs and responses

The user message body and the sender address never appear in logs or in
error responses. Three mechanisms enforce this, and all three have to hold
for the invariant to survive a careless future change:

- `common.log.ALLOWED_LOG_FIELDS` is a frozen set of structured field names.
  The `StructuredFieldsFilter` copies only fields with names from the
  allowlist into the output. `extra={"body": body}` is silently dropped.
- Problem Details responses never echo the input. `422` responses carry a
  stable `errors.validation_failed` type and a generic detail message.
- `GET /api/v1/messages/{id}` returns an explicit projection
  (`MessageView` in `services/router/src/router/api/messages.py`): status,
  department, fallback flag, error code, attempt count, timestamps. The
  sender address and body are not in the projection.

The router database does keep the full body and sender email in the
`messages` table on the `router-data` volume. There is no retention policy
in the PoC; `make clean` is the only way to remove them (it wraps the
destructive `compose down` with the volume flag, see
[operations.md](operations.md)).

## Network exposure

`docker compose up -d` publishes two ports and both are bound to `127.0.0.1`:
the router API on 8000 and the MailHog UI on 8025. The notifier (HTTP 8000
inside the stack), Ollama (11434), and MailHog SMTP (1025) are only reachable
from inside the compose networks. Three of the four compose networks are
`internal: true`, so they have no route to the outside world. The only
network with outbound access is `egress`, which Ollama uses to pull the model
from the registry on first start.

## No authentication on the API

The router API has no authentication and no rate limiting. That is why it is
only published on loopback. For anything beyond a single-developer
demonstration, this needs a token check (at minimum) at the ingress and a
real rate limiter in front of the LLM path, because an unauthenticated POST
loop will cheerfully exhaust a local model.
