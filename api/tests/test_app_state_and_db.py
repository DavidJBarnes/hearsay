"""Tests for the app-state container and the DB module."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from hearsay_api import app_state, db
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.queue import JobProcessor
from hearsay_api.storage import LocalDiskBackend


def test_get_context_unset_raises() -> None:
    """Accessing context before init raises a clear error."""
    app_state._context = None
    with pytest.raises(RuntimeError, match="not initialized"):
        app_state.get_context()


def test_context_accessors(tmp_path: object) -> None:
    """Registry/storage accessors return the installed context's members."""
    reg = EngineRegistry()
    storage = LocalDiskBackend(str(tmp_path))  # type: ignore[arg-type]
    ctx = app_state.AppContext(
        registry=reg, storage=storage, processor=JobProcessor(reg, storage), worker=None
    )
    app_state.set_context(ctx)
    assert app_state.get_registry() is reg
    assert app_state.get_storage() is storage


async def test_db_engine_singleton_and_reset() -> None:
    """get_engine/get_sessionmaker are cached; reset clears them."""
    await db.reset_engine_state()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    db.set_engine(engine)
    assert db.get_engine() is engine
    sm1 = db.get_sessionmaker()
    assert db.get_sessionmaker() is sm1
    await db.reset_engine_state()
    # After reset, a new default engine is lazily created.
    assert db.get_engine() is not engine
    await db.reset_engine_state()


async def test_get_session_dependency() -> None:
    """The session dependency yields a usable AsyncSession."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    db.set_engine(engine)
    agen = db.get_session()
    session = await agen.__anext__()
    assert isinstance(session, AsyncSession)
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    await db.reset_engine_state()
