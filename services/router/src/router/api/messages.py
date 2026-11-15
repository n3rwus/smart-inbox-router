import logging
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from common.departments import Department
from common.errors import ErrorCode
from fastapi import APIRouter, Path, Request, Response, status
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from router.application.messages import get_message, submit_message
from router.domain.message import MessageStatus
from router.ports.message_repository import MessageRepository

_log = logging.getLogger(__name__)

MESSAGE_MIN_LENGTH = 1
MESSAGE_MAX_LENGTH = 5000
MESSAGES_PATH = "/messages"
MESSAGE_BY_ID_PATH = "/messages/{message_id}"


def _trim(value: str) -> str:
    return value.strip()


MessageBody = Annotated[
    str,
    AfterValidator(_trim),
    Field(min_length=MESSAGE_MIN_LENGTH, max_length=MESSAGE_MAX_LENGTH),
]


class SubmitMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(description="Sender address used for Reply-To downstream.")
    message: MessageBody = Field(
        description=(
            f"Raw message body, {MESSAGE_MIN_LENGTH}-{MESSAGE_MAX_LENGTH} characters after "
            "trimming surrounding whitespace."
        )
    )


class SubmitMessageResponse(BaseModel):
    id: UUID
    status: MessageStatus


class MessageView(BaseModel):
    """Projection of a persisted message intentionally without the body or sender address."""

    id: UUID
    status: MessageStatus
    department: Department | None
    fallback_used: bool
    error_code: ErrorCode | None
    attempts: int
    created_at: datetime
    updated_at: datetime


router = APIRouter(prefix="/messages", tags=["messages"])


def _repository(request: Request) -> MessageRepository:
    return cast(MessageRepository, request.app.state.message_repository)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitMessageResponse,
    summary="Submit a message for routing",
    description=(
        "Accept an inbound message and enqueue it for the agent worker. "
        "The response is returned before the message is routed; "
        "poll the GET endpoint for the final status."
    ),
    responses={
        status.HTTP_202_ACCEPTED: {
            "description": "Message accepted for routing.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "4f1d1c6a-6d24-4d64-9d2c-6d00f1111111",
                        "status": "received",
                    }
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Request body failed validation.",
        },
    },
)
async def submit_message_endpoint(
    payload: SubmitMessageRequest,
    request: Request,
    response: Response,
) -> SubmitMessageResponse:
    message = await submit_message(
        sender_email=payload.email,
        body=payload.message,
        repository=_repository(request),
    )
    _log.info("message accepted", extra={"message_id": str(message.id)})
    response.headers["Location"] = f"{request.url.path.rstrip('/')}/{message.id}"
    return SubmitMessageResponse(id=message.id, status=message.status)


@router.get(
    "/{message_id}",
    response_model=MessageView,
    summary="Fetch routing status for a message",
    description=(
        "Return the current status and routing metadata for a previously submitted "
        "message. The response intentionally excludes the sender address and body "
        "to minimise data retained at the API boundary."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No message with the given id.",
        },
    },
)
async def get_message_endpoint(
    request: Request,
    message_id: Annotated[UUID, Path(description="Message id returned by POST /messages.")],
) -> MessageView:
    message = await get_message(message_id, repository=_repository(request))
    return MessageView(
        id=message.id,
        status=message.status,
        department=message.department,
        fallback_used=message.fallback_used,
        error_code=message.error_code,
        attempts=message.attempts,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )
