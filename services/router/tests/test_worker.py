import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from common.departments import Department
from common.errors import (
    DeliveryFailedError,
    ErrorCode,
    LlmUnavailableError,
    UpstreamTimeoutError,
)
from router.adapters.in_memory_message_repository import InMemoryMessageRepository
from router.agent_runner import exponential_backoff, run_worker
from router.application.worker import process_next
from router.config import RouterSettings
from router.domain.message import Message, MessageStatus
from router.ports.notifier import DeliveryRejectedError
from router.ports.routing_agent import RoutingDeps, RunStats

from .fakes import FakeNotifier


def _stats() -> RunStats:
    return RunStats(
        model="test",
        duration_ms=1,
        requests=1,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        fallback_reason=None,
    )


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
MAX_ATTEMPTS = 3
BACKOFF = timedelta(seconds=5)


def _clock(moment: datetime = NOW):
    return lambda: moment


def _backoff(_attempt: int) -> timedelta:
    return BACKOFF


async def _seeded_repo(available_at: datetime = NOW) -> tuple[InMemoryMessageRepository, UUID]:
    repo = InMemoryMessageRepository()
    message = Message(
        id=uuid4(),
        sender_email="alice@example.com",
        body="pomocy",
        created_at=NOW,
        updated_at=NOW,
        available_at=available_at,
    )
    await repo.add(message)
    return repo, message.id


class _StubAgent:
    def __init__(
        self, department: Department | None = Department.IT, error: Exception | None = None
    ) -> None:
        self._department = department
        self._error = error
        self.deps_seen: list[RoutingDeps] = []

    async def run(self, deps: RoutingDeps) -> RunStats:
        self.deps_seen.append(deps)
        if self._error is not None:
            raise self._error
        if self._department is not None:
            deps.sent_to = self._department
        return _stats()


async def test_empty_queue_returns_false() -> None:
    repo = InMemoryMessageRepository()
    agent = _StubAgent()
    notifier = FakeNotifier()

    processed = await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    assert processed is False
    assert notifier.calls == []


async def test_success_marks_sent() -> None:
    repo, message_id = await _seeded_repo()
    agent = _StubAgent(department=Department.IT)
    notifier = FakeNotifier()

    processed = await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    assert processed is True
    saved = await repo.get(message_id)
    assert saved is not None
    assert saved.status == MessageStatus.SENT
    assert saved.department is Department.IT
    assert saved.fallback_used is False


async def test_fallback_marks_sent_with_other() -> None:
    repo, message_id = await _seeded_repo()
    agent = _StubAgent(department=None)
    notifier = FakeNotifier()

    await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    saved = await repo.get(message_id)
    assert saved is not None
    assert saved.status == MessageStatus.SENT
    assert saved.department is Department.OTHER
    assert saved.fallback_used is True


@pytest.mark.parametrize(
    "error_cls",
    [LlmUnavailableError, DeliveryFailedError, UpstreamTimeoutError],
)
async def test_retryable_error_schedules_retry_before_max_attempts(
    error_cls: type[Exception],
) -> None:
    repo, message_id = await _seeded_repo()
    agent = _StubAgent(error=error_cls("boom"))
    notifier = FakeNotifier()

    await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    saved = await repo.get(message_id)
    assert saved is not None
    assert saved.status == MessageStatus.RECEIVED
    assert saved.available_at == NOW + BACKOFF


@pytest.mark.parametrize(
    ("error_cls", "expected_code"),
    [
        (LlmUnavailableError, ErrorCode.LLM_UNAVAILABLE),
        (DeliveryFailedError, ErrorCode.DELIVERY_FAILED),
        (UpstreamTimeoutError, ErrorCode.UPSTREAM_TIMEOUT),
    ],
)
async def test_retryable_error_marks_failed_after_max_attempts(
    error_cls: type[Exception], expected_code: ErrorCode
) -> None:
    repo = InMemoryMessageRepository()
    message = Message(
        id=uuid4(),
        sender_email="alice@example.com",
        body="pomocy",
        attempts=MAX_ATTEMPTS - 1,
        created_at=NOW,
        updated_at=NOW,
        available_at=NOW,
    )
    await repo.add(message)
    agent = _StubAgent(error=error_cls("boom"))
    notifier = FakeNotifier()

    await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    saved = await repo.get(message.id)
    assert saved is not None
    assert saved.status == MessageStatus.FAILED
    assert saved.error_code is expected_code


async def test_delivery_rejected_marks_failed_immediately() -> None:
    repo, message_id = await _seeded_repo()
    agent = _StubAgent(error=DeliveryRejectedError("nope"))
    notifier = FakeNotifier()

    await process_next(
        repository=repo,
        agent=agent,
        notifier=notifier,
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    saved = await repo.get(message_id)
    assert saved is not None
    assert saved.status == MessageStatus.FAILED
    assert saved.error_code is ErrorCode.DELIVERY_REJECTED


async def test_unknown_exception_marks_failed_internal_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo, message_id = await _seeded_repo()
    agent = _StubAgent(error=RuntimeError("something bad"))
    notifier = FakeNotifier()

    import logging as _logging

    with caplog.at_level(_logging.ERROR, logger="router.application.worker"):
        await process_next(
            repository=repo,
            agent=agent,
            notifier=notifier,
            clock=_clock(),
            max_attempts=MAX_ATTEMPTS,
            backoff=_backoff,
        )

    saved = await repo.get(message_id)
    assert saved is not None
    assert saved.status == MessageStatus.FAILED
    assert saved.error_code is ErrorCode.INTERNAL_ERROR
    assert any("message failed" in rec.message for rec in caplog.records)


def test_exponential_backoff_schedule() -> None:
    assert exponential_backoff(1) == timedelta(seconds=2)
    assert exponential_backoff(2) == timedelta(seconds=4)
    assert exponential_backoff(3) == timedelta(seconds=8)
    assert exponential_backoff(20).total_seconds() == 60.0


async def test_heartbeat_fires_while_process_next_blocks() -> None:
    repo, _ = await _seeded_repo()
    notifier = FakeNotifier()

    release = asyncio.Event()

    class _BlockingAgent:
        async def run(self, deps: RoutingDeps) -> RunStats:
            deps.sent_to = Department.IT
            await release.wait()
            return _stats()

    settings = RouterSettings(_env_file=None)
    stop = asyncio.Event()
    beats = 0

    def heartbeat() -> None:
        nonlocal beats
        beats += 1

    task = asyncio.create_task(
        run_worker(
            settings=settings,
            repository=repo,
            agent=_BlockingAgent(),
            notifier=notifier,
            stop=stop,
            heartbeat=heartbeat,
            heartbeat_interval_seconds=0.05,
        )
    )
    try:
        await asyncio.sleep(0.3)
        assert beats >= 3, f"expected several heartbeats while blocked, got {beats}"
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(task, timeout=2)


async def test_run_worker_stops_on_event_and_does_not_busy_loop() -> None:
    repo = InMemoryMessageRepository()
    agent = _StubAgent()
    notifier = FakeNotifier()
    settings = RouterSettings(_env_file=None)
    stop = asyncio.Event()

    poll_interval = settings.worker.poll_interval_seconds
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1

    task = asyncio.create_task(
        run_worker(
            settings=settings,
            repository=repo,
            agent=agent,
            notifier=notifier,
            stop=stop,
            heartbeat=heartbeat,
        )
    )
    await asyncio.sleep(poll_interval / 2)
    assert not task.done()
    stop.set()
    await asyncio.wait_for(task, timeout=poll_interval * 2 + 1)
    assert heartbeats >= 1
