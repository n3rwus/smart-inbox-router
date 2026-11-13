import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from common.smtp import SmtpClient
from fastapi import FastAPI

from notifier.adapters.in_memory_delivery_log import InMemoryDeliveryLog
from notifier.application.deliver import Deliver, deliver
from notifier.config import NotifierSettings
from notifier.ports.smtp_probe import SmtpProbe


@dataclass(frozen=True, slots=True)
class NotifierDependencies:
    deliver_fn: Deliver
    smtp_probe: SmtpProbe


def build_dependencies(settings: NotifierSettings) -> NotifierDependencies:
    smtp_client = SmtpClient(settings.smtp)
    log = InMemoryDeliveryLog()
    deliver_fn: Deliver = functools.partial(
        deliver,
        sender=smtp_client,
        log=log,
        from_address=settings.from_address,
    )
    return NotifierDependencies(deliver_fn=deliver_fn, smtp_probe=smtp_client)


@asynccontextmanager
async def lifespan_for(
    settings: NotifierSettings,
) -> "AsyncIterator[NotifierDependencies]":
    yield build_dependencies(settings)


def install_lifespan(app: FastAPI, settings: NotifierSettings) -> None:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with lifespan_for(settings) as deps:
            app.state.deliver = deps.deliver_fn
            app.state.smtp_probe = deps.smtp_probe
            yield

    app.router.lifespan_context = _lifespan
