import hashlib
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from common.departments import Department
from common.errors import IdempotencyConflictError
from pydantic import EmailStr

from notifier.domain.email import build_email
from notifier.ports.delivery_log import DeliveryLog
from notifier.ports.email_sender import EmailSender

_log = logging.getLogger(__name__)


class DeliveryOutcome(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"


@dataclass(frozen=True, slots=True)
class Notification:
    message_id: str
    department: Department
    sender: EmailStr
    message: str


class Deliver(Protocol):
    async def __call__(self, notification: Notification) -> DeliveryOutcome: ...


def content_hash(notification: Notification) -> str:
    h = hashlib.sha256()
    h.update(notification.department.value.encode("utf-8"))
    h.update(b"\x1f")
    h.update(notification.sender.encode("utf-8"))
    h.update(b"\x1f")
    h.update(notification.message.encode("utf-8"))
    return h.hexdigest()


async def deliver(
    notification: Notification,
    *,
    sender: EmailSender,
    log: DeliveryLog,
    from_address: EmailStr,
) -> DeliveryOutcome:
    started = time.monotonic()
    extra = {"message_id": notification.message_id, "department": notification.department.value}
    this_hash = content_hash(notification)

    async with log.lock(notification.message_id):
        stored = await log.stored_hash(notification.message_id)
        if stored is not None:
            if stored != this_hash:
                raise IdempotencyConflictError(
                    f"message_id {notification.message_id} already used for different content"
                )
            _log.info(
                "delivery skipped",
                extra={**extra, "outcome": DeliveryOutcome.ALREADY_SENT.value, "duration_ms": 0},
            )
            return DeliveryOutcome.ALREADY_SENT

        email = build_email(
            department=notification.department,
            sender=notification.sender,
            message=notification.message,
            from_address=from_address,
        )
        await sender.send(email)
        await log.record(notification.message_id, this_hash)

    _log.info(
        "delivery completed",
        extra={
            **extra,
            "outcome": DeliveryOutcome.SENT.value,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )
    return DeliveryOutcome.SENT
