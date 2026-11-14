from uuid import uuid4

import httpx
import pytest
from common.departments import Department
from common.errors import (
    DeliveryFailedError,
    LlmUnavailableError,
    UpstreamTimeoutError,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from router.adapters.routing_agent import TOOL_NAME, build_routing_agent
from router.application.route import route_message
from router.ports.notifier import DeliveryRejectedError
from router.ports.routing_agent import RoutingDeps

from .fakes import FakeNotifier


def _deps(notifier: FakeNotifier) -> RoutingDeps:
    return RoutingDeps(
        message_id=uuid4(),
        sender_email="alice@example.com",
        body="pomocy, zapomniałem hasła",
        notifier=notifier,
    )


def _response_tool(department: str) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=TOOL_NAME, args={"department": department})])


def _response_text(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def _last_has_tool_return(messages: list[ModelMessage]) -> bool:
    last = messages[-1]
    return any(isinstance(part, ToolReturnPart) for part in getattr(last, "parts", []))


async def test_tool_schema_exposes_only_department_property() -> None:
    captured: dict[str, object] = {}

    def fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["tools"] = list(info.function_tools)
        return _response_text("done")

    await build_routing_agent(FunctionModel(fn)).run(_deps(FakeNotifier()))

    tools = captured["tools"]
    assert isinstance(tools, list) and len(tools) == 1
    tool = tools[0]
    assert tool.name == TOOL_NAME
    schema = tool.parameters_json_schema
    assert set(schema["properties"]) == {"department"}
    enum_ref = schema["properties"]["department"]["$ref"].split("/")[-1]
    assert set(schema["$defs"][enum_ref]["enum"]) == {d.value for d in Department}


async def test_model_never_sees_sender_email() -> None:
    captured: list[list[ModelMessage]] = []

    def fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        captured.append(messages)
        return _response_text("done")

    await build_routing_agent(FunctionModel(fn)).run(_deps(FakeNotifier()))

    for history in captured:
        for message in history:
            for part in getattr(message, "parts", []):
                text = getattr(part, "content", None)
                if isinstance(text, str):
                    assert "alice@example.com" not in text


async def test_test_model_runs_tool_once_with_deps() -> None:
    notifier = FakeNotifier()
    adapter = build_routing_agent(TestModel(call_tools=[TOOL_NAME]))
    deps = _deps(notifier)

    await adapter.run(deps)

    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call.sender_email == deps.sender_email
    assert call.body == deps.body
    assert call.message_id == deps.message_id
    assert deps.sent_to is not None


async def test_function_model_routes_to_it() -> None:
    notifier = FakeNotifier()

    def fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if _last_has_tool_return(messages):
            return _response_text("done")
        return _response_tool(Department.IT.value)

    department, fallback = await route_message(
        message_id=uuid4(),
        sender_email="alice@example.com",
        body="Need VPN access",
        agent=build_routing_agent(FunctionModel(fn)),
        notifier=notifier,
    )

    assert department is Department.IT
    assert fallback is False
    assert len(notifier.calls) == 1
    assert notifier.calls[0].department is Department.IT


async def test_text_only_response_triggers_fallback_to_other() -> None:
    notifier = FakeNotifier()

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return _response_text("I don't know which department this is.")

    department, fallback = await route_message(
        message_id=uuid4(),
        sender_email="alice@example.com",
        body="??",
        agent=build_routing_agent(FunctionModel(fn)),
        notifier=notifier,
    )

    assert department is Department.OTHER
    assert fallback is True
    assert len(notifier.calls) == 1
    assert notifier.calls[0].department is Department.OTHER


async def test_double_tool_call_still_sends_once() -> None:
    notifier = FakeNotifier()
    calls: list[str] = []

    def fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if _last_has_tool_return(messages):
            calls.append("second")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=TOOL_NAME, args={"department": Department.HELP_DESK.value}
                    )
                ]
            )
        calls.append("first")
        return _response_tool(Department.IT.value)

    adapter = build_routing_agent(FunctionModel(fn), request_limit=5)
    deps = _deps(notifier)
    await adapter.run(deps)

    assert len(notifier.calls) == 1
    assert notifier.calls[0].department is Department.IT
    assert deps.sent_to is Department.IT


async def test_invalid_department_retries_then_falls_back() -> None:
    notifier = FakeNotifier()

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return _response_tool("legal")

    department, fallback = await route_message(
        message_id=uuid4(),
        sender_email="alice@example.com",
        body="some message",
        agent=build_routing_agent(FunctionModel(fn), request_limit=5),
        notifier=notifier,
    )

    assert fallback is True
    assert department is Department.OTHER
    assert len(notifier.calls) == 1
    assert notifier.calls[0].department is Department.OTHER


async def test_connection_error_raises_llm_unavailable_without_notifying() -> None:
    notifier = FakeNotifier()

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise httpx.ConnectError("boom")

    adapter = build_routing_agent(FunctionModel(fn))

    with pytest.raises(LlmUnavailableError):
        await route_message(
            message_id=uuid4(),
            sender_email="alice@example.com",
            body="hi",
            agent=adapter,
            notifier=notifier,
        )

    assert notifier.calls == []


NOTIFIER_ERRORS = [
    ("delivery_failed", DeliveryFailedError, "boom"),
    ("delivery_rejected", DeliveryRejectedError, "nope"),
    ("upstream_timeout", UpstreamTimeoutError, "slow"),
]


@pytest.mark.parametrize(
    ("error_cls", "message"),
    [(cls, msg) for _, cls, msg in NOTIFIER_ERRORS],
    ids=[name for name, _, _ in NOTIFIER_ERRORS],
)
async def test_notifier_error_in_tool_propagates_without_fallback(
    error_cls: type[Exception], message: str
) -> None:
    notifier = FakeNotifier(error=error_cls(message))

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return _response_tool(Department.IT.value)

    adapter = build_routing_agent(FunctionModel(fn))
    deps = _deps(notifier)

    with pytest.raises(error_cls):
        await adapter.run(deps)

    assert deps.sent_to is None
    assert len(notifier.calls) == 1


@pytest.mark.parametrize(
    ("error_cls", "message"),
    [(cls, msg) for _, cls, msg in NOTIFIER_ERRORS],
    ids=[name for name, _, _ in NOTIFIER_ERRORS],
)
async def test_route_message_does_not_fallback_when_notifier_errors(
    error_cls: type[Exception], message: str
) -> None:
    notifier = FakeNotifier(error=error_cls(message))

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return _response_tool(Department.IT.value)

    with pytest.raises(error_cls):
        await route_message(
            message_id=uuid4(),
            sender_email="alice@example.com",
            body="hi",
            agent=build_routing_agent(FunctionModel(fn)),
            notifier=notifier,
        )

    assert len(notifier.calls) == 1
