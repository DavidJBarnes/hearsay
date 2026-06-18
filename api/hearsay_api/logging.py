"""Centralized structured logging for the Hearsay API.

Every module obtains its logger through :func:`get_logger`. No module should
call :func:`logging.getLogger` directly or use ``print`` — this keeps log
formatting, levels, and context handling consistent across the service.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Structured fields attached via ``logger.info(msg, extra={"extra": {...}})``
    are merged into the emitted object so downstream collectors can index them.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as a compact JSON string."""
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger exactly once.

    Idempotent: repeated calls only adjust the level so that test setup and
    application startup can both call it safely.
    """
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(level.upper())
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring logging has been configured."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
