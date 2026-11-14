from uuid import UUID

from common.departments import Department

from router.ports.notifier import Notifier
from router.ports.routing_agent import RoutingAgent, RoutingDeps


async def route_message(
    *,
    message_id: UUID,
    sender_email: str,
    body: str,
    agent: RoutingAgent,
    notifier: Notifier,
) -> tuple[Department, bool]:
    deps = RoutingDeps(
        message_id=message_id,
        sender_email=sender_email,
        body=body,
        notifier=notifier,
    )
    await agent.run(deps)
    if deps.sent_to is not None:
        return deps.sent_to, False
    await notifier.notify(
        message_id=message_id,
        department=Department.OTHER,
        sender_email=sender_email,
        body=body,
    )
    return Department.OTHER, True
