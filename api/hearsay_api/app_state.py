"""Shared application context (engine registry, storage, worker).

Built once at startup and exposed to routers through FastAPI dependencies. Held
in a module-level slot so both the web handlers and the background worker share
the same instances.
"""

from __future__ import annotations

from dataclasses import dataclass

from hearsay_api.engines.base import EngineRegistry
from hearsay_api.queue import JobProcessor, QueueWorker
from hearsay_api.storage import StorageBackend


@dataclass(slots=True)
class AppContext:
    """Long-lived application services shared across requests."""

    registry: EngineRegistry
    storage: StorageBackend
    processor: JobProcessor
    worker: QueueWorker | None


_context: AppContext | None = None


def set_context(context: AppContext) -> None:
    """Install the active application context."""
    global _context
    _context = context


def get_context() -> AppContext:
    """Return the active application context, or raise if unset."""
    if _context is None:
        raise RuntimeError("application context not initialized")
    return _context


def get_registry() -> EngineRegistry:
    """Dependency: the engine registry."""
    return get_context().registry


def get_storage() -> StorageBackend:
    """Dependency: the storage backend."""
    return get_context().storage
