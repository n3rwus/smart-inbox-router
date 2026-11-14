"""Validate MailHog payload for the smoke test. Exit code non-zero on failure."""

import json
import os
import re
import sys

payload = os.environ["MAIL_PAYLOAD"]
message_id = os.environ["MAIL_MESSAGE_ID"]
sender = os.environ["MAIL_SENDER"]

data = json.loads(payload)
count = data.get("count", 0)
items = data.get("items") or []
if count != 1 or len(items) != 1:
    print(f"expected exactly one mail, got count={count} items={len(items)}", file=sys.stderr)
    sys.exit(4)

headers = items[0]["Content"]["Headers"]


def first(name: str) -> str:
    return (headers.get(name) or [""])[0]


reply_to = first("Reply-To")
if reply_to != sender:
    print(f"Reply-To mismatch: {reply_to!r} vs {sender!r}", file=sys.stderr)
    sys.exit(5)

to = first("To")
if not re.search(r"@example\.com>?$", to):
    print(f"To not in example.com: {to!r}", file=sys.stderr)
    sys.exit(6)

message_id_header = first("Message-ID") or first("Message-Id")
if message_id not in message_id_header:
    print(
        f"Message-ID header does not carry message id: {message_id_header!r} vs {message_id!r}",
        file=sys.stderr,
    )
    sys.exit(7)

print("smoke test OK")
