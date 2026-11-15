import functools
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from common.smtp import SmtpClient
from fastapi import FastAPI

from notifier.adapters.in_memory_delivery_log import InMemoryDeliveryLog
from notifier.application.deliver import Deliver, deliver
from notifier.config import NotifierSettings

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def build_lifespan(settings: NotifierSettings) -> Lifespan:
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

    return _lifespan
