import json
import logging
import re
import uuid

from fastapi import FastAPI, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from common.errors import INTERNAL_ERROR_CODE
from common.http.media import PROBLEM_JSON_MEDIA_TYPE
from common.log import correlation_id

CORRELATION_ID_HEADER = "X-Correlation-ID"
_HEADER_BYTES = CORRELATION_ID_HEADER.lower().encode("latin-1")
_CONTENT_TYPE_BYTES = b"content-type"
_VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_log = logging.getLogger(__name__)


def _sanitize(value: str | None) -> str:
    if value and _VALID_ID.match(value):
        return value
    return uuid.uuid4().hex


def _incoming(headers: list[tuple[bytes, bytes]]) -> str | None:
    for name, value in headers:
        if name.lower() == _HEADER_BYTES:
            return value.decode("latin-1")
    return None


def _problem_body(cid: str) -> bytes:
    return json.dumps(
        {
            "type": "about:blank",
            "title": "internal error",
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": "internal server error",
            "code": INTERNAL_ERROR_CODE,
            "correlation_id": cid,
        },
    ).encode("utf-8")


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid = _sanitize(_incoming(scope["headers"]))
        token = correlation_id.set(cid)
        header_tuple = (_HEADER_BYTES, cid.encode("latin-1"))
        response_started = False

        async def send_with_header(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers: list[tuple[bytes, bytes]] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _HEADER_BYTES
                ]
                headers.append(header_tuple)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        except Exception:
            _log.exception("unhandled error")
            if not response_started:
                body = _problem_body(cid)
                await send(
                    {
                        "type": "http.response.start",
                        "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                        "headers": [
                            (_CONTENT_TYPE_BYTES, PROBLEM_JSON_MEDIA_TYPE.encode("latin-1")),
                            (_HEADER_BYTES, cid.encode("latin-1")),
                            (b"content-length", str(len(body)).encode("latin-1")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
            raise
        finally:
            correlation_id.reset(token)


def install_correlation_middleware(app: FastAPI) -> None:
    app.add_middleware(CorrelationIdMiddleware)
