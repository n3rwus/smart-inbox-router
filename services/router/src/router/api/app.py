from common.http import (
    API_V1_DOCS_URL,
    API_V1_PREFIX,
    CorrelationIdMiddleware,
    install_problem_handlers,
)
from fastapi import FastAPI

from router.api.health import router as health_router
from router.api.messages import router as messages_router
from router.composition import install_lifespan
from router.config import RouterSettings

ROUTER_API_TITLE = "Smart Inbox Router"
ROUTER_API_VERSION = "0.1.0"
ROUTER_API_DESCRIPTION = (
    "HTTP API for the Smart Inbox Router. Accepts inbound messages and enqueues them "
    "for the agent worker, which classifies each message with a local LLM and asks "
    "the notifier service to deliver it to the right department mailbox. "
    "Errors are returned as RFC 9457 problem+json."
)


def create_app(settings: RouterSettings | None = None) -> FastAPI:
    settings = settings or RouterSettings()
    app = FastAPI(
        title=ROUTER_API_TITLE,
        description=ROUTER_API_DESCRIPTION,
        version=ROUTER_API_VERSION,
        docs_url=API_V1_DOCS_URL,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_handlers(app)
    install_lifespan(app, settings)
    app.include_router(messages_router, prefix=API_V1_PREFIX)
    app.include_router(health_router)
    return app
