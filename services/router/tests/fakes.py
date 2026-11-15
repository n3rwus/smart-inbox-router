import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from common.departments import Department
from common.errors import ErrorCode
from router.domain.message import Message, MessageNotFoundError, MessageStatus
from router.ports.notifier import DeliveryResult


@dataclass
class NotifierCall:
    message_id: UUID
    department: Department
    sender_email: str
    body: str


class FakeNotifier:
    def __init__(
        self,
        *,
        result: DeliveryResult = DeliveryResult.SENT,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[NotifierCall] = []
        self.result = result
        self.error = error

    async def notify(
        self,
        *,
        message_id: UUID,
        department: Department,
        sender_email: str,
        body: str,
    ) -> DeliveryResult:
        self.calls.append(
            NotifierCall(
                message_id=message_id,
                department=department,
                sender_email=sender_email,
                body=body,
            )
        )
        if self.error is not None:
            raise self.error
        return self.result


class InMemoryMessageRepository:
    def __init__(self) -> None:
        self._messages: dict[UUID, Message] = {}
        self._lock = asyncio.Lock()

    async def add(self, message: Message) -> None:
        async with self._lock:
            self._messages[message.id] = deepcopy(message)

    async def get(self, message_id: UUID) -> Message | None:
        async with self._lock:
            found = self._messages.get(message_id)
            return deepcopy(found) if found is not None else None

    async def claim_next(self, now: datetime) -> Message | None:
        async with self._lock:
            ready = [
                message
                for message in self._messages.values()
                if message.status == MessageStatus.RECEIVED and message.available_at <= now
            ]
            if not ready:
                return None
            ready.sort(key=lambda m: m.created_at)
            claimed = ready[0]
            claimed.start_routing(now=now)
            return deepcopy(claimed)

    async def mark_sent(
        self,
        message_id: UUID,
        department: Department,
        *,
        fallback_used: bool,
        now: datetime,
    ) -> None:
        async with self._lock:
            self._get_or_raise(message_id).mark_sent(
                department, fallback_used=fallback_used, now=now
            )

    async def mark_failed(
        self,
        message_id: UUID,
        error_code: ErrorCode,
        *,
        now: datetime,
    ) -> None:
        async with self._lock:
            self._get_or_raise(message_id).mark_failed(error_code, now=now)

    async def release_for_retry(
        self,
        message_id: UUID,
        available_at: datetime,
        *,
        now: datetime,
    ) -> None:
        async with self._lock:
            self._get_or_raise(message_id).release_for_retry(available_at, now=now)

    async def requeue_stale(self, *, now: datetime) -> int:
        async with self._lock:
            count = 0
            for message in self._messages.values():
                if message.status == MessageStatus.ROUTING:
                    message.status = MessageStatus.RECEIVED
                    message.updated_at = now
                    count += 1
            return count

    def _get_or_raise(self, message_id: UUID) -> Message:
        message = self._messages.get(message_id)
        if message is None:
            raise MessageNotFoundError(f"message {message_id} not found")
        return message
