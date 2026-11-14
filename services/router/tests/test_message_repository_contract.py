import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from common.db import create_engine, create_session_factory
from common.departments import Department
from common.errors import ErrorCode
from router.adapters.db import Base
from router.adapters.in_memory_message_repository import InMemoryMessageRepository
from router.adapters.sql_message_repository import SqlMessageRepository
from router.domain.message import Message, MessageStatus
from router.ports.message_repository import MessageRepository

RepoFactory = Callable[[], Awaitable[MessageRepository]]


def _message(
    *,
    created_at: datetime,
    available_at: datetime | None = None,
    sender: str = "alice@example.com",
) -> Message:
    return Message(
        id=uuid4(),
        sender_email=sender,
        body="hello",
        created_at=created_at,
        updated_at=created_at,
        available_at=available_at or created_at,
    )


async def _in_memory() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


@pytest.fixture
def in_memory_factory() -> RepoFactory:
    return _in_memory


@pytest.fixture
async def sql_factory(tmp_path: Path) -> AsyncIterator[RepoFactory]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'repo.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)

    async def _make() -> SqlMessageRepository:
        return SqlMessageRepository(session_factory)

    try:
        yield _make
    finally:
        await engine.dispose()


@pytest.fixture(params=["in_memory", "sql"])
async def repo(
    request: pytest.FixtureRequest,
    in_memory_factory: RepoFactory,
    sql_factory: RepoFactory,
) -> MessageRepository:
    factory = in_memory_factory if request.param == "in_memory" else sql_factory
    return await factory()


async def test_roundtrip_add_and_get(repo: MessageRepository) -> None:
    now = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    message = _message(created_at=now)
    await repo.add(message)
    fetched = await repo.get(message.id)
    assert fetched is not None
    assert fetched.id == message.id
    assert fetched.sender_email == message.sender_email
    assert fetched.status == MessageStatus.RECEIVED


async def test_get_missing_returns_none(repo: MessageRepository) -> None:
    assert await repo.get(uuid4()) is None


async def test_claim_next_returns_none_when_empty(repo: MessageRepository) -> None:
    now = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    assert await repo.claim_next(now) is None


async def test_claim_next_returns_oldest_ready(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    newer = _message(created_at=base + timedelta(minutes=5))
    older = _message(created_at=base)
    await repo.add(newer)
    await repo.add(older)
    claimed = await repo.claim_next(base + timedelta(hours=1))
    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.status == MessageStatus.ROUTING
    assert claimed.attempts == 1


async def test_claim_next_skips_future_available_at(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    future = _message(created_at=base, available_at=base + timedelta(minutes=10))
    await repo.add(future)
    assert await repo.claim_next(base) is None


async def test_concurrent_claim_next_never_double_claims(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    message = _message(created_at=base)
    await repo.add(message)
    results = await asyncio.gather(repo.claim_next(base), repo.claim_next(base))
    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1
    assert non_none[0].id == message.id


async def test_mark_sent_transitions_to_sent(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    message = _message(created_at=base)
    await repo.add(message)
    await repo.claim_next(base)
    await repo.mark_sent(
        message.id, Department.IT, fallback_used=False, now=base + timedelta(seconds=10)
    )
    saved = await repo.get(message.id)
    assert saved is not None
    assert saved.status == MessageStatus.SENT
    assert saved.department is Department.IT
    assert saved.fallback_used is False


async def test_mark_failed_transitions_to_failed(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    message = _message(created_at=base)
    await repo.add(message)
    await repo.claim_next(base)
    await repo.mark_failed(message.id, ErrorCode.ROUTING_FAILED, now=base + timedelta(seconds=10))
    saved = await repo.get(message.id)
    assert saved is not None
    assert saved.status == MessageStatus.FAILED
    assert saved.error_code is ErrorCode.ROUTING_FAILED


async def test_release_for_retry_returns_to_received(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    message = _message(created_at=base)
    await repo.add(message)
    await repo.claim_next(base)
    retry_at = base + timedelta(minutes=5)
    await repo.release_for_retry(message.id, retry_at, now=base + timedelta(seconds=10))
    saved = await repo.get(message.id)
    assert saved is not None
    assert saved.status == MessageStatus.RECEIVED
    assert saved.available_at == retry_at
    assert await repo.claim_next(base + timedelta(seconds=30)) is None
    assert (await repo.claim_next(retry_at + timedelta(seconds=1))) is not None


async def test_requeue_stale_returns_count(repo: MessageRepository) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    a = _message(created_at=base)
    b = _message(created_at=base + timedelta(seconds=1))
    await repo.add(a)
    await repo.add(b)
    await repo.claim_next(base)
    await repo.claim_next(base + timedelta(seconds=2))
    count = await repo.requeue_stale(now=base + timedelta(minutes=1))
    assert count == 2
    for message in (a, b):
        saved = await repo.get(message.id)
        assert saved is not None
        assert saved.status == MessageStatus.RECEIVED
