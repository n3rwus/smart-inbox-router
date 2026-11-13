"""RFC 9457 problem+json responses for AppError exceptions."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from common.errors import AppError, ErrorCode
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


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        http_status = STATUS_BY_CODE[exc.code]
        return JSONResponse(
            status_code=http_status,
            media_type=PROBLEM_JSON_MEDIA_TYPE,
            content={
                "type": "about:blank",
                "title": exc.code.value.replace("_", " "),
                "status": http_status,
                "detail": exc.detail,
                "code": exc.code.value,
                "correlation_id": correlation_id.get(),
            },
        )
