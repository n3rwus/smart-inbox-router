#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://127.0.0.1:8000}"
MAILHOG="${MAILHOG:-http://127.0.0.1:8025}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-2}"

SENDER="smoke-$(date +%s)-$$@example.com"
BODY='Zapomniałem hasła do konta, nie mogę się zalogować.'

echo "POST ${API}/api/v1/messages (sender=${SENDER})"
PAYLOAD=$(python3 -c 'import json, sys; print(json.dumps({"email": sys.argv[1], "message": sys.argv[2]}))' "${SENDER}" "${BODY}")
POST_RESPONSE=$(curl -fsS -X POST "${API}/api/v1/messages" \
  -H 'Content-Type: application/json' \
  -d "${PAYLOAD}")
MESSAGE_ID=$(printf '%s' "${POST_RESPONSE}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')
echo "message id: ${MESSAGE_ID}"

echo "poll GET /api/v1/messages/${MESSAGE_ID} up to ${TIMEOUT_SECONDS}s"
DEADLINE=$(( $(date +%s) + TIMEOUT_SECONDS ))
STATUS=""
LAST_BODY=""
while :; do
  LAST_BODY=$(curl -fsS "${API}/api/v1/messages/${MESSAGE_ID}")
  STATUS=$(printf '%s' "${LAST_BODY}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", ""))')
  if [[ "${STATUS}" == "sent" || "${STATUS}" == "failed" ]]; then
    break
  fi
  if (( $(date +%s) >= DEADLINE )); then
    echo "timeout waiting for terminal status; last status='${STATUS}' body=${LAST_BODY}" >&2
    exit 2
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

if [[ "${STATUS}" != "sent" ]]; then
  echo "message did not reach 'sent': body=${LAST_BODY}" >&2
  exit 3
fi
echo "message routed: ${LAST_BODY}"

echo "checking MailHog for one matching mail"
MAIL_RESPONSE=$(curl -fsS "${MAILHOG}/api/v2/search?kind=containing&query=${MESSAGE_ID}")
MAIL_PAYLOAD="${MAIL_RESPONSE}" MAIL_MESSAGE_ID="${MESSAGE_ID}" MAIL_SENDER="${SENDER}" \
  python3 "$(dirname "$0")/_smoke_check_mail.py"
