"""RFC 9457 problem+json responses for all unhandled exceptions."""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.errors import INTERNAL_ERROR_CODE, AppError, ErrorCode
from common.http.media import PROBLEM_JSON_MEDIA_TYPE
from common.log import correlation_id

STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_SENDER: status.HTTP_400_BAD_REQUEST,
    ErrorCode.LLM_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.ROUTING_FAILED: status.HTTP_502_BAD_GATEWAY,
    ErrorCode.DELIVERY_FAILED: status.HTTP_502_BAD_GATEWAY,
    ErrorCode.MESSAGE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.UPSTREAM_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ErrorCode.IDEMPOTENCY_CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.NOT_READY: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _phrase(http_status: int) -> str:
    try:
        return HTTPStatus(http_status).phrase
    except ValueError:
        return "HTTP Error"


def _code_from_status(http_status: int) -> str:
    return _phrase(http_status).lower().replace(" ", "_").replace("-", "_") or "http_error"


def _problem_response(
    *,
    http_status: int,
    code: str,
    title: str | None = None,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": "about:blank",
        "title": title or _phrase(http_status),
        "status": http_status,
        "code": code,
        "correlation_id": correlation_id.get(),
    }
    if detail is not None:
        content["detail"] = detail
    if extra:
        content.update(extra)
    return JSONResponse(
        status_code=http_status,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        content=content,
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _problem_response(
            http_status=STATUS_BY_CODE[exc.code],
            code=exc.code.value,
            title=exc.code.value.replace("_", " "),
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return _problem_response(
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_failed",
            extra={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
        return _problem_response(
            http_status=exc.status_code,
            code=_code_from_status(exc.status_code),
            detail=detail,
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, __: Exception) -> JSONResponse:
        return _problem_response(
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=INTERNAL_ERROR_CODE,
        )
