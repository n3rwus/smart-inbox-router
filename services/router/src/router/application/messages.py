from datetime import UTC, datetime
from uuid import UUID, uuid4

from router.domain.message import Message, MessageNotFoundError
from router.ports.message_repository import MessageRepository


async def submit_message(
    *,
    sender_email: str,
    body: str,
    repository: MessageRepository,
    now: datetime | None = None,
) -> Message:
    moment = now or datetime.now(UTC)
    message = Message(
        id=uuid4(),
        sender_email=sender_email,
        body=body,
        created_at=moment,
        updated_at=moment,
        available_at=moment,
    )
    await repository.add(message)
    return message


async def get_message(message_id: UUID, *, repository: MessageRepository) -> Message:
    message = await repository.get(message_id)
    if message is None:
        raise MessageNotFoundError(f"message {message_id} not found")
    return message
