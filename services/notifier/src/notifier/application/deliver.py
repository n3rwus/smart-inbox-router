from dataclasses import dataclass
from enum import StrEnum

from common.departments import Department
from pydantic import EmailStr

from notifier.domain.email import build_email
from notifier.ports.delivery_log import DeliveryLog
from notifier.ports.email_sender import EmailSender


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
    if await log.is_delivered(notification.message_id):
        return DeliveryOutcome.ALREADY_SENT

    email = build_email(
        department=notification.department,
        sender=notification.sender,
        message=notification.message,
        from_address=from_address,
    )
    await sender.send(email)
    await log.mark_delivered(notification.message_id)
    return DeliveryOutcome.SENT
