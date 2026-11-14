import asyncio
import contextlib
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from common.db import create_engine, create_session_factory
from common.log import configure_logging
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from router.adapters.http_notifier import HttpNotifier
from router.adapters.routing_agent import build_routing_agent
from router.adapters.sql_message_repository import SqlMessageRepository
from router.application.worker import process_next
from router.config import RouterSettings
from router.ports.routing_agent import RoutingAgent

BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0

_log = logging.getLogger("router.agent_runner")


def exponential_backoff(attempts: int) -> timedelta:
    delay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS**attempts)
    return timedelta(seconds=delay)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def run_worker(
    *,
    settings: RouterSettings,
    repository: SqlMessageRepository,
    agent: RoutingAgent,
    notifier: HttpNotifier,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = _utcnow,
    heartbeat: Callable[[], None] | None = None,
) -> None:
    poll_interval = settings.worker.poll_interval_seconds
    while not stop.is_set():
        if heartbeat is not None:
            heartbeat()
        processed = await process_next(
            repository=repository,
            agent=agent,
            notifier=notifier,
            clock=clock,
            max_attempts=settings.worker.max_attempts,
            backoff=exponential_backoff,
        )
        if processed:
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)


async def _main_async() -> None:
    settings = RouterSettings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    repository = SqlMessageRepository(session_factory)

    notifier = HttpNotifier(
        base_url=settings.notifier.base_url,
        timeout_seconds=settings.notifier.timeout_seconds,
        max_retries=settings.notifier.max_retries,
    )
    model = OpenAIChatModel(
        settings.llm.model,
        provider=OllamaProvider(base_url=settings.llm.base_url),
    )
    agent = build_routing_agent(model, timeout_seconds=settings.llm.timeout_seconds)

    stale = await repository.requeue_stale(now=_utcnow())
    _log.info("requeued stale messages on startup", extra={"attempt": stale})

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    heartbeat_path = Path(settings.worker.heartbeat_path)
    try:
        await run_worker(
            settings=settings,
            repository=repository,
            agent=agent,
            notifier=notifier,
            stop=stop,
            heartbeat=lambda: _touch(heartbeat_path),
        )
    finally:
        await notifier.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
