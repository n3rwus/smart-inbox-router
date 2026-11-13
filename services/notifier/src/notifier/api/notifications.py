from typing import Annotated, cast
from uuid import UUID

from common.departments import Department
from common.http import API_V1_PREFIX
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr

from notifier.application.deliver import Deliver, DeliveryOutcome, Notification

NOTIFICATIONS_PATH = "/notifications"


class NotificationBody(BaseModel):
    department: Department
    sender: EmailStr
    body: str

    def to_notification(self, message_id: str) -> Notification:
        return Notification(
            message_id=message_id,
            department=self.department,
            sender=self.sender,
            message=self.body,
        )


def get_deliver(request: Request) -> Deliver:
    return cast(Deliver, request.app.state.deliver)


router = APIRouter(tags=["notifications"])


@router.put(
    f"{NOTIFICATIONS_PATH}/{{message_id}}",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"description": "Replay of an already-delivered message"},
        status.HTTP_409_CONFLICT: {"description": "message_id reused with different content"},
        status.HTTP_502_BAD_GATEWAY: {"description": "SMTP server rejected or unreachable"},
        status.HTTP_504_GATEWAY_TIMEOUT: {"description": "SMTP server did not answer in time"},
    },
)
async def put_notification(
    message_id: UUID,
    payload: NotificationBody,
    response: Response,
    deliver_fn: Annotated[Deliver, Depends(get_deliver)],
) -> None:
    outcome = await deliver_fn(payload.to_notification(str(message_id)))
    if outcome is DeliveryOutcome.SENT:
        response.status_code = status.HTTP_201_CREATED
        response.headers["Location"] = f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}/{message_id}"
    else:
        response.status_code = status.HTTP_200_OK
