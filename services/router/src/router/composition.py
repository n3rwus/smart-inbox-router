from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from common.db import create_engine, create_session_factory
from fastapi import FastAPI

from router.adapters.sql_message_repository import SqlMessageRepository
from router.api.health import READY_TIMEOUT_SECONDS, SessionDbReadyProbe
from router.config import RouterSettings

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def build_lifespan(settings: RouterSettings) -> Lifespan:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        session_factory = create_session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.db_probe = SessionDbReadyProbe(session_factory, READY_TIMEOUT_SECONDS)
        app.state.message_repository = SqlMessageRepository(session_factory)
        try:
            yield
        finally:
            await engine.dispose()

    return _lifespan
