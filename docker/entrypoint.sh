#!/bin/sh
# Container entrypoint: selects the process based on the first argument.
#   api      – HTTP server (default)
#   agent    – AI agent runner (only for SERVICE=router)
#   migrate  – database migrations
#   <other>  – any command, e.g. python, sh
set -eu

: "${SERVICE:?Missing SERVICE environment variable (router|notifier)}"
PORT="${PORT:-8000}"

cmd="${1:-api}"
if [ "$#" -gt 0 ]; then shift; fi

case "$cmd" in
  api)
    exec uvicorn "${SERVICE}.main:app" \
      --host 0.0.0.0 \
      --port "${PORT}" \
      --timeout-graceful-shutdown 30 \
      "$@"
    ;;
  agent)
    if [ "$SERVICE" != "router" ]; then
      echo "agent: only available for SERVICE=router (current: ${SERVICE})" >&2
      exit 64
    fi
    exec python -m router.agent_runner "$@"
    ;;
  migrate)
    exec python -m "${SERVICE}.migrate" "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
