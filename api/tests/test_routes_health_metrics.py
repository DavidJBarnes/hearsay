"""Tests for health, readiness, and metrics endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_healthz(app_client: AsyncClient) -> None:
    """Liveness returns ok."""
    resp = await app_client.get("/healthz")
    assert resp.json() == {"status": "ok"}


async def test_readyz_ready(app_client: AsyncClient) -> None:
    """Readiness reports ready when DB and context are up."""
    resp = await app_client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert "kokoro" in body["engines"]


async def test_readyz_not_ready_without_context(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness reports 503 when the context is missing."""

    def _raise() -> None:
        raise RuntimeError("no context")

    monkeypatch.setattr("hearsay_api.routers.health.get_context", _raise)
    resp = await app_client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["context"] is False


async def test_readyz_db_failure(app_client: AsyncClient) -> None:
    """Readiness reports the database as down on query failure."""
    from fastapi import Response

    from hearsay_api.routers.health import readyz

    class BrokenSession:
        async def execute(self, *a: object, **k: object) -> None:
            raise RuntimeError("db down")

    response = Response()
    result = await readyz(response, BrokenSession())  # type: ignore[arg-type]
    assert response.status_code == 503
    assert result["database"] is False
    assert "db down" in result["database_error"]  # type: ignore[operator]


async def test_metrics_endpoint(app_client: AsyncClient) -> None:
    """The metrics endpoint returns Prometheus text."""
    resp = await app_client.get("/metrics")
    assert resp.status_code == 200
    assert "hearsay_" in resp.text
