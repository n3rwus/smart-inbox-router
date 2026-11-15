from common.http import (
    API_V1_DOCS_URL,
    API_V1_PREFIX,
    CorrelationIdMiddleware,
    install_problem_handlers,
)
from fastapi import FastAPI

from notifier.api.health import router as health_router
from notifier.api.notifications import router as notifications_router
from notifier.composition import build_lifespan
from notifier.config import NotifierSettings


def create_app(settings: NotifierSettings | None = None) -> FastAPI:
    settings = settings or NotifierSettings()
    app = FastAPI(
        docs_url=API_V1_DOCS_URL,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        lifespan=build_lifespan(settings),
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_handlers(app)
    app.include_router(notifications_router, prefix=API_V1_PREFIX)
    app.include_router(health_router)
    return app
