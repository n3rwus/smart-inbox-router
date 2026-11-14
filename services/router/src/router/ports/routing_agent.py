from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from common.departments import Department

from router.ports.notifier import Notifier


@dataclass
class RoutingDeps:
    message_id: UUID
    sender_email: str
    body: str
    notifier: Notifier
    sent_to: Department | None = None


class RoutingAgent(Protocol):
    async def run(self, deps: RoutingDeps) -> None: ...
