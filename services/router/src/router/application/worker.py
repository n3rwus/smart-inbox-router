import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from common.errors import (
    DeliveryFailedError,
    ErrorCode,
    LlmUnavailableError,
    UpstreamTimeoutError,
)
from common.log import correlation_id

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

    message_id_str = str(message.id)
    token = correlation_id.set(message_id_str)
    try:
        queue_wait_ms = max(0, int((now - message.created_at).total_seconds() * 1000))
        _log.info(
            "message claimed",
            extra={
                "message_id": message_id_str,
                "attempt": message.attempts,
                "queue_wait_ms": queue_wait_ms,
            },
        )
        started_at = clock()
        try:
            department, fallback_used, stats = await route_message(
                message_id=message.id,
                sender_email=message.sender_email,
                body=message.body,
                agent=agent,
                notifier=notifier,
            )
        except DeliveryRejectedError as exc:
            finished_at = clock()
            await repository.mark_failed(message.id, exc.code, now=finished_at)
            _log.error(
                "message failed",
                extra={
                    "message_id": message_id_str,
                    "error_code": exc.code.value,
                    "error_type": type(exc).__name__,
                    "attempt": message.attempts,
                },
            )
            return True
        except (LlmUnavailableError, DeliveryFailedError, UpstreamTimeoutError) as exc:
            finished_at = clock()
            if message.attempts < max_attempts:
                retry_delay = backoff(message.attempts)
                available_at = finished_at + retry_delay
                await repository.release_for_retry(message.id, available_at, now=finished_at)
                _log.warning(
                    "message retry scheduled",
                    extra={
                        "message_id": message_id_str,
                        "attempt": message.attempts,
                        "error_code": exc.code.value,
                        "error_type": type(exc).__name__,
                        "retry_in_seconds": retry_delay.total_seconds(),
                    },
                )
            else:
                await repository.mark_failed(message.id, exc.code, now=finished_at)
                _log.error(
                    "message failed",
                    extra={
                        "message_id": message_id_str,
                        "error_code": exc.code.value,
                        "error_type": type(exc).__name__,
                        "attempt": message.attempts,
                    },
                )
            return True
        except Exception as exc:
            finished_at = clock()
            await repository.mark_failed(message.id, ErrorCode.INTERNAL_ERROR, now=finished_at)
            _log.exception(
                "message failed",
                extra={
                    "message_id": message_id_str,
                    "error_code": ErrorCode.INTERNAL_ERROR.value,
                    "error_type": type(exc).__name__,
                    "attempt": message.attempts,
                },
            )
            return True

        _log.info(
            "llm run finished",
            extra={
                "message_id": message_id_str,
                "model": stats.model,
                "duration_ms": stats.duration_ms,
                "requests": stats.requests,
                "tool_calls": stats.tool_calls,
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
            },
        )
        if stats.fallback_reason is not None:
            _log.warning(
                "routing fallback used",
                extra={"message_id": message_id_str, "reason": stats.fallback_reason},
            )

        finished_at = clock()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        await repository.mark_sent(
            message.id, department, fallback_used=fallback_used, now=finished_at
        )
        _log.info(
            "message routed",
            extra={
                "message_id": message_id_str,
                "department": department.value,
                "fallback_used": fallback_used,
                "duration_ms": duration_ms,
                "attempt": message.attempts,
            },
        )
        return True
    finally:
        correlation_id.reset(token)
