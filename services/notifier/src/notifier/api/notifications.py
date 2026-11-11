from collections.abc import Awaitable, Callable
from typing import Annotated

from common.departments import Department
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, field_validator

from notifier.application.deliver import DeliveryOutcome, Notification

NOTIFICATIONS_PATH = "/notifications"

DeliverHandler = Callable[[Notification], Awaitable[DeliveryOutcome]]


class NotificationRequest(BaseModel):
    message_id: str
    department: Department
    sender: EmailStr
    body: str

    @field_validator("message_id")
    @classmethod
    def _reject_crlf_in_message_id(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("CR/LF not allowed in message_id")
        return value

    def to_notification(self) -> Notification:
        return Notification(
            message_id=self.message_id,
            department=self.department,
            sender=self.sender,
            message=self.body,
        )


def get_deliver() -> DeliverHandler:
    raise NotImplementedError("overridden in the composition root")


router = APIRouter(tags=["notifications"])


@router.post(
    NOTIFICATIONS_PATH,
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"description": "SMTP server rejected or unreachable"},
        status.HTTP_504_GATEWAY_TIMEOUT: {"description": "SMTP server did not answer in time"},
    },
)
async def create_notification(
    payload: NotificationRequest,
    deliver_fn: Annotated[DeliverHandler, Depends(get_deliver)],
) -> None:
    await deliver_fn(payload.to_notification())
