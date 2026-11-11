from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_SENDER = "invalid_sender"
    LLM_UNAVAILABLE = "llm_unavailable"
    ROUTING_FAILED = "routing_failed"
    DELIVERY_FAILED = "delivery_failed"
    MESSAGE_NOT_FOUND = "message_not_found"
    UPSTREAM_TIMEOUT = "upstream_timeout"


class AppError(Exception):
    code: ErrorCode

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DeliveryFailedError(AppError):
    code = ErrorCode.DELIVERY_FAILED


class UpstreamTimeoutError(AppError):
    code = ErrorCode.UPSTREAM_TIMEOUT
