from common.http import API_V1_DOCS_URL, API_V1_PREFIX, install_problem_handlers
from fastapi import FastAPI

from notifier.api.notifications import router as notifications_router


def create_app() -> FastAPI:
    app = FastAPI(docs_url=API_V1_DOCS_URL, openapi_url=f"{API_V1_PREFIX}/openapi.json")
    install_problem_handlers(app)
    app.include_router(notifications_router, prefix=API_V1_PREFIX)
    return app
