from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from common.departments import Department

from router.ports.notifier import Notifier

FallbackReason = Literal["no_tool_call", "usage_limit", "unexpected_model_behavior"]


@dataclass
class RoutingDeps:
    message_id: UUID
    sender_email: str
    body: str
    notifier: Notifier
    sent_to: Department | None = None


@dataclass
class RunStats:
    model: str
    duration_ms: int
    requests: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    fallback_reason: FallbackReason | None


class RoutingAgent(Protocol):
    async def run(self, deps: RoutingDeps) -> RunStats: ...
