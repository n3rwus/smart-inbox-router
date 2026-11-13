import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from common.departments import Department
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


async def deliver(
    notification: Notification,
    *,
    sender: EmailSender,
    log: DeliveryLog,
    from_address: EmailStr,
) -> DeliveryOutcome:
    started = time.monotonic()
    extra = {"message_id": notification.message_id, "department": notification.department.value}

    async with log.lock(notification.message_id):
        if await log.is_delivered(notification.message_id):
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
        await log.mark_delivered(notification.message_id)

    _log.info(
        "delivery completed",
        extra={
            **extra,
            "outcome": DeliveryOutcome.SENT.value,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )
    return DeliveryOutcome.SENT
