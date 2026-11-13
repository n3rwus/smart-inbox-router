import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

ALLOWED_LOG_FIELDS: frozenset[str] = frozenset(
    {"message_id", "department", "outcome", "duration_ms", "status_code"}
)

_TEXT_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s%(structured_text)s"
)


def _stringify(value: Any) -> Any:
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get() or "-"
        return True


class StructuredFieldsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        structured = {
            name: _stringify(getattr(record, name))
            for name in ALLOWED_LOG_FIELDS
            if hasattr(record, name)
        }
        record.structured = structured
        record.structured_text = (
            " " + " ".join(f"{k}={v}" for k, v in structured.items()) if structured else ""
        )
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        payload.update(getattr(record, "structured", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationFilter())
    handler.addFilter(StructuredFieldsFilter())
    handler.setFormatter(JsonFormatter() if json_output else logging.Formatter(_TEXT_FORMAT))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
