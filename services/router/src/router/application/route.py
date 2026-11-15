from uuid import UUID

from common.departments import Department

from router.ports.notifier import Notifier
from router.ports.routing_agent import RoutingAgent, RoutingDeps, RunStats


async def route_message(
    *,
    message_id: UUID,
    sender_email: str,
    body: str,
    agent: RoutingAgent,
    notifier: Notifier,
) -> tuple[Department, bool, RunStats]:
    deps = RoutingDeps(
        message_id=message_id,
        sender_email=sender_email,
        body=body,
        notifier=notifier,
    )
    stats = await agent.run(deps)
    if deps.sent_to is not None:
        return deps.sent_to, False, stats
    await notifier.notify(
        message_id=message_id,
        department=Department.OTHER,
        sender_email=sender_email,
        body=body,
    )
    return Department.OTHER, True, stats
