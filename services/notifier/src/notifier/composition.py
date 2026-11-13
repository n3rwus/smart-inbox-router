import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.smtp import SmtpClient
from fastapi import FastAPI

from notifier.adapters.in_memory_delivery_log import InMemoryDeliveryLog
from notifier.application.deliver import Deliver, deliver
from notifier.config import NotifierSettings


def install_lifespan(app: FastAPI, settings: NotifierSettings) -> None:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        smtp_client = SmtpClient(settings.smtp)
        deliver_fn: Deliver = functools.partial(
            deliver,
            sender=smtp_client,
            log=InMemoryDeliveryLog(),
            from_address=settings.from_address,
        )
        app.state.deliver = deliver_fn
        app.state.smtp_probe = smtp_client
        yield

    app.router.lifespan_context = _lifespan
