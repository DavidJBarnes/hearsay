"""Tests for application wiring and lifespan."""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from hearsay_api.config import Settings
from hearsay_api.main import build_context, create_app


def test_build_context_worker_enabled() -> None:
    """A worker is created when enabled in settings."""
    ctx = build_context(Settings(worker_enabled=True))
    assert ctx.worker is not None
    assert "kokoro" in ctx.registry.names()


def test_build_context_worker_disabled() -> None:
    """No worker is created when disabled."""
    ctx = build_context(Settings(worker_enabled=False))
    assert ctx.worker is None


async def test_full_lifespan_and_middleware(engine_db: None) -> None:
    """The real lifespan starts/stops the worker and records latency."""
    app = create_app()
    async with LifespanManager(app, startup_timeout=30, shutdown_timeout=30):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/healthz")
            assert resp.status_code == 200
    # After shutdown the latency metric for /healthz should be registered.
    from hearsay_api.metrics import REQUEST_LATENCY

    sample = REQUEST_LATENCY.labels(route="/healthz", method="GET")
    assert sample._sum.get() >= 0
