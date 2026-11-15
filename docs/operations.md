# Operations

This file covers what you do once `docker compose up -d` has brought the
stack up: how to tell it is ready, where the healthchecks look, how to read
the logs, how to peek into the queue, how to change the model, and how to
recover when something gets stuck.

## Start-up and readiness

A clean `docker compose up -d` builds two images (router, notifier), starts
the long-running services, and runs two one-shot jobs (`ollama-init`,
`router-migrate`). The stack is ready when every long-running service has a
`healthy` status and both one-shot jobs have exited with code 0:

    docker compose ps
    docker compose logs -f ollama-init

Expected steady state:

    router-api      Up   (healthy)
    router-agent    Up   (healthy)
    notifier        Up   (healthy)
    ollama          Up   (healthy)
    mailhog         Up
    router-migrate  Exited (0)
    ollama-init     Exited (0)

The first start takes a few minutes because `ollama-init` downloads
`qwen2.5:3b` (about 1.9 GB). Later starts reuse the model on the
`ollama-models` volume.

## Healthchecks

Every container-level `healthcheck:` in `docker-compose.yml` is a thin
Python probe. They check the following:

- `router-api` and `notifier`: HTTP `GET /ready` on `127.0.0.1:8000`
  (inside the container). `/ready` is a liveness-plus-readiness check;
  for the notifier it opens an SMTP probe (see
  `notifier.ports.smtp_probe`). If SMTP is down, `/ready` returns `503`
  and the container stays `unhealthy`.
- `router-agent`: checks that `/data/router-agent.alive` was touched in
  the last 30 seconds. The worker touches that file every 5 seconds from
  a background `asyncio` task. If the main loop is stuck inside an LLM
  call for longer than the LLM timeout (default 120 s), the file keeps
  getting touched and the container stays healthy; a real deadlock stops
  the touches and the container goes unhealthy within a probe cycle.
- `ollama`: `ollama list`. Starts returning success as soon as the
  server can list local models, even before the pull finishes.
- `mailhog`: no container healthcheck (the image does not ship one), only
  the HTTP UI on 8025.

## Reading the logs

Logs are plain text by default (`LOG_JSON=false`), with structured fields
appended as `key=value` pairs. Set `LOG_JSON=true` to switch to one JSON
object per line.

A typical routed message produces five log lines on the router agent:

    message claimed        message_id=... attempt=1 queue_wait_ms=42
    routing tool called    department=help-desk
    notifier call finished message_id=... attempt=1 duration_ms=57 outcome=sent status_code=201
    llm run finished       message_id=... model=qwen2.5:3b duration_ms=612 requests=1 tool_calls=1 input_tokens=... output_tokens=...
    message routed         message_id=... department=help-desk fallback_used=False duration_ms=1070 attempt=1

Recipes with `jq` when `LOG_JSON=true`:

- One message end to end, by `message_id`:

      docker compose logs router-api router-agent notifier \
        | jq -c 'select(.message_id == "68470cf5-4c1f-446e-a54a-37a26d4f05f9")'

- Errors only:

      docker compose logs router-agent | jq -c 'select(.level == "ERROR" or .level == "WARNING")'

- Fallback runs:

      docker compose logs router-agent | jq -c 'select(.msg == "routing fallback used")'

- Tool calls (how often the model actually called `send_to_department`):

      docker compose logs router-agent | jq -c 'select(.msg == "llm run finished") | {message_id, tool_calls}'

The log allowlist (`common.log.ALLOWED_LOG_FIELDS`) guarantees that only
named structured fields appear. The user message body and the sender
address are not in the allowlist and cannot leak into the logs through
`extra={}`.

## Peeking into the queue

The database lives on the `smart-inbox-router_router-data` named volume,
inside the router images. A small SQLite query from inside the
`router-api` container:

    docker compose exec router-api python -c "
    import sqlite3
    c = sqlite3.connect('/data/router.db')
    for row in c.execute('SELECT status, COUNT(*) FROM messages GROUP BY status'):
        print(row)
    "

Or the last 10 messages:

    docker compose exec router-api python -c "
    import sqlite3
    c = sqlite3.connect('/data/router.db')
    for row in c.execute('SELECT id, status, department, attempts, created_at FROM messages ORDER BY created_at DESC LIMIT 10'):
        print(row)
    "

## Changing the model

The model name is `OLLAMA_MODEL` (default `qwen2.5:3b`). It is read by both
`ollama-init` (for the pull) and `router-agent` (for the LLM client), so
they stay in sync:

    OLLAMA_MODEL=qwen2.5:7b docker compose up -d

After a model change, `ollama-init` reruns the pull. Expect a few minutes
and roughly 4 GB extra disk for a 7B model. The agent picks the new model
on its next restart (it is read at process start).

## LLM timeout and graceful shutdown

The agent has one critical interaction: `ROUTER_LLM__TIMEOUT_SECONDS`
(default 120 s) must be less than compose's `stop_grace_period`
(130 s on `router-agent`). On `docker compose stop`, the worker receives
`SIGTERM`, sets its `asyncio.Event`, and finishes the current message
before exiting. If the LLM call is slower than the grace period, the
container is `SIGKILL` sent mid-call and the message is left in `routing`;
on the next start, `requeue_stale()` flips it back to `received`.

## Resetting the database

For a clean queue without rebuilding Ollama or wiping the model cache,
remove only the router volume:

    docker compose rm -sf router-api router-agent router-migrate
    docker volume rm smart-inbox-router_router-data
    docker compose up -d

Never run `make clean` or the destructive compose teardown unless you
want to lose the downloaded model as well; that wipes `ollama-models`
too and the next start downloads the 1.9 GB again.

## Troubleshooting

### Stale image after code changes

`docker compose up -d` does not rebuild if the image tag already exists.
After editing source files:

    docker compose up -d --build

Or build the images explicitly with `make images` first.

### First message is slow

Ollama keeps models unloaded until first use. The first request after a
`docker compose up -d` can take up to a minute while the model is loaded
into memory. Subsequent requests are well under a second (eval p50 is
583 ms, p95 is 1381 ms on `qwen2.5:3b`).

### Notifier is unhealthy right after `compose up`

Check the two SMTP variables the container actually received:

    docker compose exec notifier printenv NOTIFIER_SMTP__HOST NOTIFIER_SMTP__PORT

The expected values are `mailhog` and `1025`. If you see `localhost`,
you have a host `.env` being pulled in through `env_file`. The compose
file sets these two explicitly after `env_file`, so compose v2.24+
should win; on older compose versions `env_file` could still shadow
them. Upgrade compose or remove the stray values from your host `.env`.

### cannot start a paused container

Happens in tests that use `docker compose pause`. The `unpause` must run
before the next `start`. Clean up with:

    docker compose unpause router-agent
    docker compose start router-agent

### The agent is healthy but the queue does not drain

Check whether Ollama is reachable from the agent network:

    docker compose exec router-agent python -c "
    import httpx, asyncio
    async def main():
        async with httpx.AsyncClient() as c:
            r = await c.get('http://ollama:11434/v1/models')
            print(r.status_code)
    asyncio.run(main())
    "

A failure here usually means `ollama-init` never finished the pull; look
at `docker compose logs ollama-init`.
