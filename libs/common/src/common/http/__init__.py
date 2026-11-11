from common.http.problems import STATUS_BY_CODE, install_problem_handlers

API_V1_PREFIX = "/api/v1"
API_V1_DOCS_URL = f"{API_V1_PREFIX}/docs"
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

__all__ = [
    "API_V1_DOCS_URL",
    "API_V1_PREFIX",
    "PROBLEM_JSON_MEDIA_TYPE",
    "STATUS_BY_CODE",
    "install_problem_handlers",
]
