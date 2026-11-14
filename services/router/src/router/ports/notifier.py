from enum import StrEnum
from typing import Protocol
from uuid import UUID

from common.departments import Department
from common.errors import AppError, ErrorCode


class DeliveryResult(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"


class DeliveryRejectedError(AppError):
    code = ErrorCode.DELIVERY_REJECTED


class Notifier(Protocol):
    async def notify(
        self,
        *,
        message_id: UUID,
        department: Department,
        sender_email: str,
        body: str,
    ) -> DeliveryResult: ...
