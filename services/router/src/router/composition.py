from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.db import create_engine, create_session_factory
from fastapi import FastAPI

from router.adapters.sql_message_repository import SqlMessageRepository
from router.api.health import READY_TIMEOUT_SECONDS, SessionDbReadyProbe
from router.config import RouterSettings


def install_lifespan(app: FastAPI, settings: RouterSettings) -> None:
    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
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

    app.router.lifespan_context = _lifespan
