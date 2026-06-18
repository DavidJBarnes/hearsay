"""Tests for the GPU daemon logging module."""

from __future__ import annotations

import json
import logging

from hearsay_gpu import logging as glog


def test_formatter_includes_service_and_extra() -> None:
    """Records are tagged with the gpu service and merge extras."""
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    record.extra = {"k": "v"}
    out = json.loads(glog.JsonFormatter().format(record))
    assert out["service"] == "gpu"
    assert out["k"] == "v"


def test_formatter_exception() -> None:
    """Exception info is serialized when present."""
    import sys

    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "x", logging.ERROR, __file__, 1, "f", None, sys.exc_info()
        )
    assert "boom" in json.loads(glog.JsonFormatter().format(record))["exc"]


def test_configure_idempotent_and_get_logger() -> None:
    """Configuration is idempotent and get_logger configures on demand."""
    glog._CONFIGURED = False
    glog.configure_logging("INFO")
    count = len(logging.getLogger().handlers)
    glog.configure_logging("DEBUG")
    assert len(logging.getLogger().handlers) == count
    glog._CONFIGURED = False
    assert isinstance(glog.get_logger("x"), logging.Logger)
    assert glog._CONFIGURED is True
