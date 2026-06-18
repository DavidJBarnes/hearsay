"""Tests for centralized logging."""

from __future__ import annotations

import json
import logging

from hearsay_api import logging as hlog


def test_json_formatter_includes_extra_and_exc() -> None:
    """The formatter merges structured extras and exception info."""
    formatter = hlog.JsonFormatter()
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    record.extra = {"engine": "kokoro"}
    out = json.loads(formatter.format(record))
    assert out["msg"] == "hello"
    assert out["engine"] == "kokoro"
    assert out["level"] == "INFO"


def test_json_formatter_exception() -> None:
    """Exception info is serialized when present."""
    formatter = hlog.JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "fail", None, sys.exc_info())
    out = json.loads(formatter.format(record))
    assert "boom" in out["exc"]


def test_configure_logging_idempotent() -> None:
    """Configuring twice does not stack handlers; level still updates."""
    hlog._CONFIGURED = False
    hlog.configure_logging("INFO")
    count = len(logging.getLogger().handlers)
    hlog.configure_logging("DEBUG")
    assert len(logging.getLogger().handlers) == count
    assert logging.getLogger().level == logging.DEBUG


def test_get_logger_configures_when_needed() -> None:
    """``get_logger`` configures logging if not already configured."""
    hlog._CONFIGURED = False
    logger = hlog.get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert hlog._CONFIGURED is True
