import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from common.errors import (
    DeliveryFailedError,
    ErrorCode,
    LlmUnavailableError,
    UpstreamTimeoutError,
)

from router.application.route import route_message
from router.ports.message_repository import MessageRepository
from router.ports.notifier import DeliveryRejectedError, Notifier
from router.ports.routing_agent import RoutingAgent

Clock = Callable[[], datetime]
BackoffFn = Callable[[int], timedelta]

_log = logging.getLogger(__name__)


async def process_next(
    *,
    repository: MessageRepository,
    agent: RoutingAgent,
    notifier: Notifier,
    clock: Clock,
    max_attempts: int,
    backoff: BackoffFn,
) -> bool:
    now = clock()
    message = await repository.claim_next(now)
    if message is None:
        return False

    _log.info(
        "message claimed",
        extra={"message_id": str(message.id), "attempt": message.attempts},
    )
    started_at = clock()
    try:
        department, fallback_used = await route_message(
            message_id=message.id,
            sender_email=message.sender_email,
            body=message.body,
            agent=agent,
            notifier=notifier,
        )
    except DeliveryRejectedError as exc:
        finished_at = clock()
        await repository.mark_failed(message.id, exc.code, now=finished_at)
        _log.warning(
            "message failed",
            extra={"message_id": str(message.id), "status_code": exc.code.value},
        )
        return True
    except (LlmUnavailableError, DeliveryFailedError, UpstreamTimeoutError) as exc:
        finished_at = clock()
        if message.attempts < max_attempts:
            available_at = finished_at + backoff(message.attempts)
            await repository.release_for_retry(message.id, available_at, now=finished_at)
            _log.warning(
                "message retry scheduled",
                extra={
                    "message_id": str(message.id),
                    "attempt": message.attempts,
                    "status_code": exc.code.value,
                },
            )
        else:
            await repository.mark_failed(message.id, exc.code, now=finished_at)
            _log.warning(
                "message failed",
                extra={"message_id": str(message.id), "status_code": exc.code.value},
            )
        return True
    except Exception:
        finished_at = clock()
        await repository.mark_failed(message.id, ErrorCode.INTERNAL_ERROR, now=finished_at)
        _log.exception(
            "message failed",
            extra={
                "message_id": str(message.id),
                "status_code": ErrorCode.INTERNAL_ERROR.value,
            },
        )
        return True

    finished_at = clock()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    await repository.mark_sent(message.id, department, fallback_used=fallback_used, now=finished_at)
    _log.info(
        "message routed",
        extra={
            "message_id": str(message.id),
            "department": department.value,
            "fallback_used": fallback_used,
            "duration_ms": duration_ms,
        },
    )
    return True
