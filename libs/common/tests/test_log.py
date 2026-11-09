import json
import logging
import sys

from common.log import CorrelationFilter, JsonFormatter, configure_logging, correlation_id


def _record() -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("x",), None)


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
