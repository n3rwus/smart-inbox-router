import logging
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID, uuid4

import pytest
from common.departments import Department
from common.log import (
    ALLOWED_LOG_FIELDS,
    CorrelationFilter,
    JsonFormatter,
    StructuredFieldsFilter,
    correlation_id,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from router.adapters.routing_agent import TOOL_NAME, build_routing_agent
from router.application.worker import process_next
from router.domain.message import Message
from router.ports.routing_agent import RoutingDeps, RunStats

from .fakes import FakeNotifier, InMemoryMessageRepository

_build_agent = partial(build_routing_agent, timeout_seconds=60.0)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SENDER = "very-unique-sender-xyz@example.com"
SECRET_FRAGMENT = "SUPER-SECRET-LEAK-TOKEN-7A3F"  # noqa: S105
BODY = f"please help, {SECRET_FRAGMENT}"
MAX_ATTEMPTS = 3
BACKOFF = timedelta(seconds=5)


def _clock(moment: datetime = NOW):
    return lambda: moment


def _backoff(_a: int) -> timedelta:
    return BACKOFF


async def _seed_message(repo: InMemoryMessageRepository, *, body: str = BODY) -> UUID:
    created = NOW - timedelta(seconds=2)
    message = Message(
        id=uuid4(),
        sender_email=SENDER,
        body=body,
        created_at=created,
        updated_at=created,
        available_at=created,
    )
    await repo.add(message)
    return message.id


def _response_tool(department: str) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=TOOL_NAME, args={"department": department})])


def _response_text(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def _last_has_tool_return(messages: list[ModelMessage]) -> bool:
    last = messages[-1]
    return any(isinstance(part, ToolReturnPart) for part in getattr(last, "parts", []))


def _records_by_message(caplog: pytest.LogCaptureFixture, msg: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.message == msg]


def _one(caplog: pytest.LogCaptureFixture, msg: str) -> logging.LogRecord:
    found = _records_by_message(caplog, msg)
    assert len(found) == 1, f"expected one {msg!r}, got {len(found)}"
    return found[0]


async def test_process_next_sets_correlation_id_and_restores(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryMessageRepository()
    message_id = await _seed_message(repo)

    def fn(messages: list[ModelMessage], _i: AgentInfo) -> ModelResponse:
        if _last_has_tool_return(messages):
            return _response_text("done")
        return _response_tool(Department.IT.value)

    agent = _build_agent(FunctionModel(fn), model_name="qwen2.5:3b")
    notifier = FakeNotifier()

    outer = correlation_id.set("outside")
    seen_during: list[str | None] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name.startswith("router."):
                seen_during.append(correlation_id.get())

    handler = _Capture()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        caplog.set_level(logging.DEBUG)
        await process_next(
            repository=repo,
            agent=agent,
            notifier=notifier,
            clock=_clock(),
            max_attempts=MAX_ATTEMPTS,
            backoff=_backoff,
        )
        assert correlation_id.get() == "outside"
    finally:
        root.removeHandler(handler)
        correlation_id.reset(outer)

    expected = str(message_id)
    assert seen_during, "expected worker log records"
    for cid in seen_during:
        assert cid == expected, f"cid during logging was {cid!r}, expected {expected!r}"


async def test_message_claimed_logs_queue_wait(caplog: pytest.LogCaptureFixture) -> None:
    repo = InMemoryMessageRepository()
    message_id = await _seed_message(repo)
    agent_called = {"ran": False}

    class _A:
        async def run(self, deps: RoutingDeps) -> RunStats:
            agent_called["ran"] = True
            deps.sent_to = Department.IT
            return RunStats(
                model="m",
                duration_ms=1,
                requests=1,
                tool_calls=1,
                input_tokens=10,
                output_tokens=2,
                fallback_reason=None,
            )

    caplog.set_level(logging.INFO)
    await process_next(
        repository=repo,
        agent=_A(),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    rec = _one(caplog, "message claimed")
    assert rec.levelno == logging.INFO
    assert rec.message_id == str(message_id)  # type: ignore[attr-defined]
    assert rec.attempt == 1  # type: ignore[attr-defined]
    assert rec.queue_wait_ms == 2000  # type: ignore[attr-defined]


async def test_llm_run_finished_and_message_routed_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryMessageRepository()
    message_id = await _seed_message(repo)

    class _A:
        async def run(self, deps: RoutingDeps) -> RunStats:
            deps.sent_to = Department.IT
            return RunStats(
                model="qwen2.5:3b",
                duration_ms=42,
                requests=1,
                tool_calls=1,
                input_tokens=100,
                output_tokens=20,
                fallback_reason=None,
            )

    caplog.set_level(logging.INFO)
    await process_next(
        repository=repo,
        agent=_A(),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    llm = _one(caplog, "llm run finished")
    assert llm.model == "qwen2.5:3b"  # type: ignore[attr-defined]
    assert llm.requests == 1  # type: ignore[attr-defined]
    assert llm.tool_calls == 1  # type: ignore[attr-defined]
    assert llm.input_tokens == 100  # type: ignore[attr-defined]
    assert llm.output_tokens == 20  # type: ignore[attr-defined]
    assert llm.duration_ms == 42  # type: ignore[attr-defined]

    routed = _one(caplog, "message routed")
    assert routed.levelno == logging.INFO
    assert routed.message_id == str(message_id)  # type: ignore[attr-defined]
    assert routed.department == Department.IT.value  # type: ignore[attr-defined]
    assert routed.fallback_used is False  # type: ignore[attr-defined]
    assert routed.attempt == 1  # type: ignore[attr-defined]
    assert isinstance(routed.duration_ms, int)  # type: ignore[attr-defined]
    assert not _records_by_message(caplog, "routing fallback used")


async def test_routing_fallback_used_logged_on_text_only_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryMessageRepository()
    await _seed_message(repo)

    def fn(_m: list[ModelMessage], _i: AgentInfo) -> ModelResponse:
        return _response_text("i don't know")

    caplog.set_level(logging.INFO)
    await process_next(
        repository=repo,
        agent=_build_agent(FunctionModel(fn), model_name="qwen2.5:3b"),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    fb = _one(caplog, "routing fallback used")
    assert fb.levelno == logging.WARNING
    assert fb.reason == "no_tool_call"  # type: ignore[attr-defined]

    routed = _one(caplog, "message routed")
    assert routed.fallback_used is True  # type: ignore[attr-defined]
    assert routed.department == Department.OTHER.value  # type: ignore[attr-defined]


async def test_routing_tool_called_logged(caplog: pytest.LogCaptureFixture) -> None:
    repo = InMemoryMessageRepository()
    await _seed_message(repo)

    def fn(messages: list[ModelMessage], _i: AgentInfo) -> ModelResponse:
        if _last_has_tool_return(messages):
            return _response_text("done")
        return _response_tool(Department.HELP_DESK.value)

    caplog.set_level(logging.INFO)
    await process_next(
        repository=repo,
        agent=_build_agent(FunctionModel(fn), model_name="m"),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    rec = _one(caplog, "routing tool called")
    assert rec.department == Department.HELP_DESK.value  # type: ignore[attr-defined]


async def test_message_retry_scheduled_fields(caplog: pytest.LogCaptureFixture) -> None:
    from common.errors import LlmUnavailableError

    repo = InMemoryMessageRepository()
    message_id = await _seed_message(repo)

    class _A:
        async def run(self, deps: RoutingDeps) -> RunStats:
            raise LlmUnavailableError("down")

    caplog.set_level(logging.WARNING)
    await process_next(
        repository=repo,
        agent=_A(),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    rec = _one(caplog, "message retry scheduled")
    assert rec.levelno == logging.WARNING
    assert rec.message_id == str(message_id)  # type: ignore[attr-defined]
    assert rec.error_code == "llm_unavailable"  # type: ignore[attr-defined]
    assert rec.error_type == "LlmUnavailableError"  # type: ignore[attr-defined]
    assert rec.attempt == 1  # type: ignore[attr-defined]
    assert rec.retry_in_seconds == BACKOFF.total_seconds()  # type: ignore[attr-defined]


async def test_message_failed_fields_after_max_attempts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from common.errors import LlmUnavailableError

    repo = InMemoryMessageRepository()
    created = NOW - timedelta(seconds=1)
    message = Message(
        id=uuid4(),
        sender_email=SENDER,
        body=BODY,
        attempts=MAX_ATTEMPTS - 1,
        created_at=created,
        updated_at=created,
        available_at=created,
    )
    await repo.add(message)

    class _A:
        async def run(self, deps: RoutingDeps) -> RunStats:
            raise LlmUnavailableError("down")

    caplog.set_level(logging.ERROR)
    await process_next(
        repository=repo,
        agent=_A(),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    rec = _one(caplog, "message failed")
    assert rec.levelno == logging.ERROR
    assert rec.error_code == "llm_unavailable"  # type: ignore[attr-defined]
    assert rec.error_type == "LlmUnavailableError"  # type: ignore[attr-defined]
    assert rec.attempt == MAX_ATTEMPTS  # type: ignore[attr-defined]


async def test_submit_message_logs_message_accepted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryMessageRepository()
    caplog.set_level(logging.INFO)

    class _Repo:
        def __init__(self) -> None:
            self.stored: list[Message] = []

        async def add(self, m: Message) -> None:
            self.stored.append(m)

    from fastapi.testclient import TestClient
    from router.api.app import create_app
    from router.config import RouterSettings

    settings = RouterSettings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.message_repository = repo
        resp = client.post(
            "/api/v1/messages",
            json={"email": "a@b.co", "message": "hi"},
        )
    assert resp.status_code == 202
    accepted = _one(caplog, "message accepted")
    assert accepted.levelno == logging.INFO
    assert accepted.message_id == resp.json()["id"]  # type: ignore[attr-defined]


async def test_log_payloads_do_not_leak_sender_or_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryMessageRepository()
    await _seed_message(repo)

    def fn(messages: list[ModelMessage], _i: AgentInfo) -> ModelResponse:
        if _last_has_tool_return(messages):
            return _response_text("done")
        return _response_tool(Department.IT.value)

    caplog.set_level(logging.DEBUG)
    await process_next(
        repository=repo,
        agent=_build_agent(FunctionModel(fn), model_name="m"),
        notifier=FakeNotifier(),
        clock=_clock(),
        max_attempts=MAX_ATTEMPTS,
        backoff=_backoff,
    )

    cfilter = CorrelationFilter()
    sfilter = StructuredFieldsFilter()
    jformatter = JsonFormatter()
    tformatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s%(structured_text)s"
    )

    for rec in caplog.records:
        cfilter.filter(rec)
        sfilter.filter(rec)
        for line in (jformatter.format(rec), tformatter.format(rec)):
            assert SENDER not in line, f"sender leaked into log: {line}"
            assert SECRET_FRAGMENT not in line, f"body fragment leaked into log: {line}"

        structured = getattr(rec, "structured", {})
        for key in structured:
            assert key in ALLOWED_LOG_FIELDS
