"""FastAPI application factory and lifespan wiring.

Builds the engine registry and storage backend, provisions the bootstrap API
key, starts the queue worker, and mounts all routers. A middleware records
request latency into the Prometheus registry.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from hearsay_api.app_state import AppContext, set_context
from hearsay_api.auth import ensure_bootstrap_key
from hearsay_api.config import Settings, get_settings
from hearsay_api.db import get_sessionmaker
from hearsay_api.engines.base import EngineError
from hearsay_api.engines.placement import build_registry
from hearsay_api.logging import configure_logging, get_logger
from hearsay_api.metrics import REQUEST_LATENCY
from hearsay_api.queue import JobProcessor, QueueWorker
from hearsay_api.routers import health, jobs, metrics_routes, openai_compat, realtime, voices
from hearsay_api.storage import build_storage

log = get_logger(__name__)


def build_context(settings: Settings) -> AppContext:
    """Construct the application context from settings (no side effects)."""
    registry = build_registry(settings)
    storage = build_storage(settings)
    processor = JobProcessor(registry, storage)
    worker: QueueWorker | None = None
    if settings.worker_enabled:
        worker = QueueWorker(
            get_sessionmaker(),
            processor,
            poll_interval_s=settings.worker_poll_interval_s,
        )
    return AppContext(registry=registry, storage=storage, processor=processor, worker=worker)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize context, bootstrap key, and the worker for the app's life."""
    settings = get_settings()
    configure_logging(settings.log_level)
    context = build_context(settings)
    set_context(context)

    async with get_sessionmaker()() as session:
        await ensure_bootstrap_key(session)

    if context.worker is not None:
        context.worker.start()
    log.info("hearsay api started", extra={"extra": {"engines": context.registry.names()}})
    try:
        yield
    finally:
        if context.worker is not None:
            await context.worker.stop()
        log.info("hearsay api stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Hearsay", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(EngineError)
    async def _engine_error_handler(request: Request, exc: EngineError) -> JSONResponse:
        """Return an engine failure with its real cause and upstream status."""
        log.warning("engine call failed", extra={"extra": {"detail": exc.detail}})
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.middleware("http")
    async def _latency_middleware(request: Request, call_next: object) -> Response:
        """Record per-route request latency."""
        start = time.perf_counter()
        response: Response = await call_next(request)  # type: ignore[operator]
        REQUEST_LATENCY.labels(route=request.url.path, method=request.method).observe(
            time.perf_counter() - start
        )
        return response

    app.include_router(health.router)
    app.include_router(metrics_routes.router)
    app.include_router(openai_compat.router)
    app.include_router(voices.router)
    app.include_router(jobs.router)
    app.include_router(realtime.router)
    return app


app = create_app()
