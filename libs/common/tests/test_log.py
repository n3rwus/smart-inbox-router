import json
import logging
import sys
import uuid
from enum import StrEnum

from common.log import (
    _TEXT_FORMAT,
    CorrelationFilter,
    JsonFormatter,
    StructuredFieldsFilter,
    configure_logging,
    correlation_id,
)


def _record(extra: dict[str, object] | None = None) -> logging.LogRecord:
    rec = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    if extra:
        for k, v in extra.items():
            setattr(rec, k, v)
    return rec


def test_json_line_carries_correlation_id():
    token = correlation_id.set("msg-1")
    try:
        record = _record()
        CorrelationFilter().filter(record)
        line = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id.reset(token)

    assert line["correlation_id"] == "msg-1"
    assert line["msg"] == "hello x"
    assert line["level"] == "INFO"


def test_missing_correlation_id_is_dash():
    record = _record()
    CorrelationFilter().filter(record)
    assert record.correlation_id == "-"


def test_json_line_includes_exception():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    CorrelationFilter().filter(record)
    assert "RuntimeError: boom" in json.loads(JsonFormatter().format(record))["exc"]


def test_json_includes_allowlisted_fields() -> None:
    record = _record({"message_id": "m1", "department": "it", "outcome": "sent", "duration_ms": 12})
    CorrelationFilter().filter(record)
    StructuredFieldsFilter().filter(record)

    line = json.loads(JsonFormatter().format(record))

    assert line["message_id"] == "m1"
    assert line["department"] == "it"
    assert line["outcome"] == "sent"
    assert line["duration_ms"] == 12


def test_json_drops_non_allowlisted_fields() -> None:
    record = _record({"sender": "jan@example.pl", "body": "tajne", "message_id": "m1"})
    CorrelationFilter().filter(record)
    StructuredFieldsFilter().filter(record)

    line = json.loads(JsonFormatter().format(record))

    assert "sender" not in line
    assert "body" not in line
    assert "jan@example.pl" not in JsonFormatter().format(record)
    assert line["message_id"] == "m1"


def test_json_serialises_uuid_and_enum_values() -> None:
    class _Dept(StrEnum):
        IT = "it"

    mid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    record = _record({"message_id": mid, "department": _Dept.IT})
    CorrelationFilter().filter(record)
    StructuredFieldsFilter().filter(record)

    line = json.loads(JsonFormatter().format(record))

    assert line["message_id"] == str(mid)
    assert line["department"] == "it"


def test_text_appends_allowlisted_fields() -> None:
    record = _record({"message_id": "m1", "outcome": "sent", "sender": "jan@example.pl"})
    CorrelationFilter().filter(record)
    StructuredFieldsFilter().filter(record)

    line = logging.Formatter(_TEXT_FORMAT).format(record)

    assert "message_id=m1" in line
    assert "outcome=sent" in line
    assert "jan@example.pl" not in line
    assert "sender=" not in line


def test_configure_logging_installs_single_handler():
    configure_logging("DEBUG", json_output=True)
    root = logging.getLogger()
    try:
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers.clear()
        root.setLevel(logging.WARNING)
