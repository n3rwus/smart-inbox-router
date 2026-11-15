# Changelog

All notable changes to this project follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-16

First release: the Smart Inbox Router PoC — a classifier-and-forwarder pipeline
for inbound messages built around a local LLM (Ollama) and a notifier service.

### Features

- `router` HTTP API: `POST /api/v1/messages` enqueues inbound messages, worker
  classifies each one with a pydantic-ai agent against an OpenAI-compatible LLM
  (Ollama) and dispatches it to the notifier.
- `notifier` HTTP API: idempotent `PUT /api/v1/notifications/{message_id}`,
  delivery over SMTP with a recipient allowlist; `/ready` probes SMTP.
- Department catalog is server-side and the LLM only picks a `Department` enum;
  Reply-To and recipient are set from the request, never from model output.
- Agent worker with graceful shutdown (SIGTERM) and heartbeat for container
  healthchecks; retry + fallback path when the LLM is unavailable.
- Docker Compose stack with Ollama (no auth, internal network), MailHog, and
  one-shot Alembic migration job. Routing evaluation runner with report.
- Structured JSON logs with correlation id, LLM usage, and notifier outcome.

### Fixes

- Map pydantic-ai `ModelConnectionError` to `LlmUnavailableError`.
- Keep the agent heartbeat alive during long model calls.
- Build router image on plain `docker compose up`; expose model choice via env.

### Docs

- Architecture, operations, security, development guides and ADRs in `docs/`.
- Rewritten README with quick start and cURL example.

[0.1.0]: https://github.com/n3rwus/smart-inbox-router/releases/tag/v0.1.0
