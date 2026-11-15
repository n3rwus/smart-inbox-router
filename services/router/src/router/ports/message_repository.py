from datetime import datetime
from typing import Protocol
from uuid import UUID

from common.departments import Department
from common.errors import ErrorCode

from router.domain.message import Message


class MessageRepository(Protocol):
    async def add(self, message: Message) -> None: ...

    async def get(self, message_id: UUID) -> Message | None: ...

    async def claim_next(self, now: datetime) -> Message | None: ...

    async def mark_sent(
        self,
        message_id: UUID,
        department: Department,
        *,
        fallback_used: bool,
        now: datetime,
    ) -> None: ...

    async def mark_failed(
        self,
        message_id: UUID,
        error_code: ErrorCode,
        *,
        now: datetime,
    ) -> None: ...

    async def release_for_retry(
        self,
        message_id: UUID,
        available_at: datetime,
        *,
        now: datetime,
    ) -> None: ...

    async def requeue_stale(self, *, now: datetime) -> int: ...
