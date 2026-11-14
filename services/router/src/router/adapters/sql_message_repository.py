from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from common.departments import Department
from common.errors import ErrorCode
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from router.adapters.db.message_row import MessageRow
from router.domain.message import (
    InvalidMessageStateError,
    Message,
    MessageNotFoundError,
    MessageStatus,
)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row_to_message(row: MessageRow) -> Message:
    return Message(
        id=UUID(row.id),
        sender_email=row.sender_email,
        body=row.body,
        status=MessageStatus(row.status),
        department=Department(row.department) if row.department is not None else None,
        fallback_used=row.fallback_used,
        error_code=ErrorCode(row.error_code) if row.error_code is not None else None,
        attempts=row.attempts,
        created_at=_as_aware_utc(row.created_at),
        updated_at=_as_aware_utc(row.updated_at),
        available_at=_as_aware_utc(row.available_at),
    )


def _message_to_row(message: Message) -> MessageRow:
    return MessageRow(
        id=str(message.id),
        sender_email=message.sender_email,
        body=message.body,
        status=message.status.value,
        department=message.department.value if message.department is not None else None,
        fallback_used=message.fallback_used,
        error_code=message.error_code.value if message.error_code is not None else None,
        attempts=message.attempts,
        created_at=_as_naive_utc(message.created_at),
        updated_at=_as_naive_utc(message.updated_at),
        available_at=_as_naive_utc(message.available_at),
    )


class SqlMessageRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, message: Message) -> None:
        async with self._session_factory() as session:
            session.add(_message_to_row(message))
            await session.commit()

    async def get(self, message_id: UUID) -> Message | None:
        async with self._session_factory() as session:
            row = await session.get(MessageRow, str(message_id))
            return _row_to_message(row) if row is not None else None

    async def claim_next(self, now: datetime) -> Message | None:
        naive_now = _as_naive_utc(now)
        oldest = (
            select(MessageRow.id)
            .where(
                MessageRow.status == MessageStatus.RECEIVED.value,
                MessageRow.available_at <= naive_now,
            )
            .order_by(MessageRow.created_at.asc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            update(MessageRow)
            .where(MessageRow.id == oldest, MessageRow.status == MessageStatus.RECEIVED.value)
            .values(
                status=MessageStatus.ROUTING.value,
                attempts=MessageRow.attempts + 1,
                updated_at=naive_now,
            )
            .returning(MessageRow)
            .execution_options(synchronize_session=False)
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            return _row_to_message(row) if row is not None else None

    async def mark_sent(
        self,
        message_id: UUID,
        department: Department,
        *,
        fallback_used: bool,
        now: datetime,
    ) -> None:
        await self._transition(
            message_id,
            from_status=MessageStatus.ROUTING,
            values={
                "status": MessageStatus.SENT.value,
                "department": department.value,
                "fallback_used": fallback_used,
                "error_code": None,
                "updated_at": _as_naive_utc(now),
            },
        )

    async def mark_failed(
        self,
        message_id: UUID,
        error_code: ErrorCode,
        *,
        now: datetime,
    ) -> None:
        await self._transition(
            message_id,
            from_status=MessageStatus.ROUTING,
            values={
                "status": MessageStatus.FAILED.value,
                "error_code": error_code.value,
                "updated_at": _as_naive_utc(now),
            },
        )

    async def release_for_retry(
        self,
        message_id: UUID,
        available_at: datetime,
        *,
        now: datetime,
    ) -> None:
        await self._transition(
            message_id,
            from_status=MessageStatus.ROUTING,
            values={
                "status": MessageStatus.RECEIVED.value,
                "available_at": _as_naive_utc(available_at),
                "updated_at": _as_naive_utc(now),
            },
        )

    async def requeue_stale(self, *, now: datetime) -> int:
        stmt = (
            update(MessageRow)
            .where(MessageRow.status == MessageStatus.ROUTING.value)
            .values(
                status=MessageStatus.RECEIVED.value,
                updated_at=_as_naive_utc(now),
            )
            .execution_options(synchronize_session=False)
        )
        async with self._session_factory() as session:
            result = cast(CursorResult[object], await session.execute(stmt))
            await session.commit()
            return result.rowcount or 0

    async def _transition(
        self,
        message_id: UUID,
        *,
        from_status: MessageStatus,
        values: dict[str, object],
    ) -> None:
        stmt = (
            update(MessageRow)
            .where(MessageRow.id == str(message_id), MessageRow.status == from_status.value)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        async with self._session_factory() as session:
            result = cast(CursorResult[object], await session.execute(stmt))
            if result.rowcount == 0:
                existing = await session.get(MessageRow, str(message_id))
                if existing is None:
                    raise MessageNotFoundError(f"message {message_id} not found")
                raise InvalidMessageStateError(
                    f"cannot transition message {message_id} from status {existing.status}: "
                    f"expected {from_status.value}"
                )
            await session.commit()
