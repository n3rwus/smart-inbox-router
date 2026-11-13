from common.http.correlation import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
    install_correlation_middleware,
)
from common.http.problems import STATUS_BY_CODE, install_problem_handlers
from common.http.server import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    HttpServerConfig,
)

API_V1_PREFIX = "/api/v1"
API_V1_DOCS_URL = f"{API_V1_PREFIX}/docs"
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

__all__ = [
    "API_V1_DOCS_URL",
    "API_V1_PREFIX",
    "CORRELATION_ID_HEADER",
    "DEFAULT_HTTP_HOST",
    "DEFAULT_HTTP_PORT",
    "PROBLEM_JSON_MEDIA_TYPE",
    "STATUS_BY_CODE",
    "CorrelationIdMiddleware",
    "HttpServerConfig",
    "install_correlation_middleware",
    "install_problem_handlers",
]
