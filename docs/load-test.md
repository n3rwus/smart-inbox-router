# Load test — phase A (intake)

Tool: [`scripts/load_test.py`](../scripts/load_test.py) — stdlib only, threaded POST loop against `/api/v1/messages`. Target: `make load` (defaults `INTAKE=200 CONCURRENCY=50`, override via env).

## Setup

- Full stack via `docker compose up -d`.
- `docker compose stop router-agent` so the queue only fills; no routing.
- Shared volume `smart-inbox-router_router-data` on SQLite (WAL, `busy_timeout=5000`).

## Run

```text
$ make load
python3 scripts/load_test.py --intake 200 --concurrency 50
intake=200 concurrency=50 wall=2624ms
accepted(202)=200  server_errors(5xx)=0  other=0
latency p50=395.7ms p95=1590.0ms max=2610.3ms
```

- 200/200 responses were `202 Accepted`.
- Zero 5xx.
- `docker compose logs router-api | grep -iE "database is locked|500|internal server"` returned no matches.
- SQLite row count after the run: `SELECT status, COUNT(*) FROM messages GROUP BY status` → `[('received', 200)]`.

| metric | value |
| --- | ---: |
| intake | 200 |
| concurrency | 50 |
| wall time | 2624 ms |
| accepted (202) | 200 |
| server errors (5xx) | 0 |
| latency p50 | 395.7 ms |
| latency p95 | 1590.0 ms |
| latency max | 2610.3 ms |

## Crash test (pending)

Recipe from the ticket (volume cleanup was skipped on request so the 200 pending rows could drain through the agent instead of being deleted; re-run this on a clean `router-data` volume to produce the evidence):

1. `docker compose down`, `docker volume rm smart-inbox-router_router-data`, `docker compose up -d`.
2. POST one message.
3. `docker compose kill router-agent` while the model is still answering.
4. `docker compose start router-agent`.

Expected: the message returns to `received` via `requeue_stale()` at startup, is re-processed, and MailHog shows exactly one mail for its id with `attempts=2` in the GET response (reviewer to paste the real numbers).
