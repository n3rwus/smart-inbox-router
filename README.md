- RFC 9457 Problem Details

```JSON
{
  "type": "about:blank",
  "title": "Message not found",
  "status": 404,
  "detail": "No message with id 7f3c...",
  "code": "message_not_found",
  "request_id": "a1b2c3"
}
```

- Jeśli wysyłka się uda, a zapis w logu nie, ponowna próba wyśle maila drugi raz. Wyścig przy sprawdzaniu i zapisie

### Decision: notifier as a separate service over HTTP

The notifier runs as its own container and owns email delivery: recipient
allowlist, `Reply-To`, idempotency. The router calls it via
`PUT /api/v1/notifications/{message_id}` through a `Notifier` port, so the
transport can change without touching the agent.

**Security invariant:** the agent's tool `send_to_department(department)`
takes only the department enum from the LLM. Message id, sender address and
body are attached by router code, never by the model, so prompt injection in
a message cannot change recipients or `Reply-To`.

**Trade-off:** an extra container and an HTTP client with timeouts, in exchange
for independent deployment and a real service boundary. The notifier is
internal only — no published port, reachable only from the router over the
`notify-net` compose network. An MCP interface was considered and skipped as
unnecessary for this PoC. There is no authentication between router and
notifier; both live on an internal compose network, which is good enough for
the PoC and will need mTLS or a shared secret before any external exposure.

### Notifier HTTP contract

| Endpoint | Semantics |
|----------|-----------|
| `PUT /api/v1/notifications/{message_id}` | Idempotent send. `message_id` is a UUID in the path. Body: `department`, `sender`, `body` — no recipient or `Reply-To`, notifier sets both. |
| `GET /health` | Liveness, always 200 (`include_in_schema=False`). |
| `GET /ready` | Readiness: connects to SMTP (NOOP, no mail sent). 200 or Problem Details 503 (`not_ready`). Compose healthcheck targets this endpoint on `127.0.0.1`. |

Response codes on PUT:

- **201 Created** with `Location` header — the mail was just sent.
- **200 OK** — the same `message_id` had already been delivered with identical
  content (department, sender, body); no new mail is sent.
- **409 Conflict** (`idempotency_conflict`) — the same `message_id` was reused
  with a different body. `DeliveryLog` keeps a SHA-256 hash of the content
  under each id to detect this without storing the message text.
- **422 / 502 / 504** as Problem Details, as before.

### Correlation ID

Every request carries `X-Correlation-ID`. Missing or malformed values are
replaced by a server-generated UUID. The id is echoed back on the response
(including 500 and Problem Details responses) and attached to log records
and OTel spans via a ContextVar.

### Idempotency log is in-memory for the PoC

`DeliveryLog` is a process-local dict guarded by per-`message_id` locks.
A single notifier replica guarantees exactly-once per id for its lifetime.
After a restart the memory is gone — a router retry across the restart can
produce a duplicate mail. Each outgoing message carries a deterministic
`Message-ID: <{message_id}@notifier.smart-inbox-router>`, so a recipient's
mailbox can still dedupe post-restart duplicates. The upgrade path is a
SQL-backed adapter behind the same `DeliveryLog` port.

### Notifier SMTP config

SMTP connection comes from nested env vars (`NOTIFIER_SMTP__*`). Against the
default MailHog target `NOTIFIER_SMTP__START_TLS=false`, because MailHog does
not support TLS. Point the same variables at a real SMTP server and flip
`START_TLS` to `true`; no code change needed.

### Running integration tests

Integration tests are deselected from the default `make test` run via the
`integration` pytest marker. They run as a container joined to the
`mail-net` network so MailHog's SMTP port stays unpublished to the host:

```bash
docker compose up -d mailhog
make test-integration
```

The `integration-tests` service in `docker-compose.test.yml` injects
`MAILHOG_*` env vars that point at the `mailhog` service by name.
