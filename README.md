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
`POST /api/v1/notifications` through a `Notifier` port, so the transport can
change without touching the agent.

**Security invariant:** the agent's tool `send_to_department(department)`
takes only the department enum from the LLM. Message id, sender address and
body are attached by router code, never by the model, so prompt injection in
a message cannot change recipients or `Reply-To`.

**Trade-off:** an extra container and an HTTP client with timeouts, in exchange
for independent deployment and a real service boundary. The notifier is
internal only (no published port). An MCP interface was considered and skipped
as unnecessary for this PoC.

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
