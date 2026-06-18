"""Liveness and readiness endpoints.

``/healthz`` is a pure liveness check. ``/readyz`` verifies the database is
reachable and the application context (engines/storage) is initialized.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hearsay_api.app_state import get_context
from hearsay_api.db import get_session
from hearsay_api.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return a static liveness response."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    response: Response, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    """Verify DB connectivity and context readiness."""
    checks: dict[str, object] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001 - report DB failure as not-ready
        checks["database"] = False
        checks["database_error"] = str(exc)
    try:
        ctx = get_context()
        checks["engines"] = ctx.registry.names()
        checks["context"] = True
    except RuntimeError:
        checks["context"] = False
    ready = checks.get("database") is True and checks.get("context") is True
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    checks["ready"] = ready
    return checks
