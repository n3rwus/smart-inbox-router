import re
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from common.log import correlation_id

CORRELATION_ID_HEADER = "X-Correlation-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


def _sanitize(value: str | None) -> str:
    if value and _VALID_ID.match(value):
        return value
    return uuid.uuid4().hex


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = _sanitize(request.headers.get(CORRELATION_ID_HEADER))
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers[CORRELATION_ID_HEADER] = cid
        return response


def install_correlation_middleware(app: FastAPI) -> None:
    app.add_middleware(CorrelationIdMiddleware)
