"""Async SQLAlchemy engine, session factory, and declarative base.

The engine is created lazily from settings so tests can override the database
URL before the first session is requested.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from hearsay_api.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the cached session factory bound to the async engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session per request."""
    async with get_sessionmaker()() as session:
        yield session


async def reset_engine_state() -> None:
    """Dispose the engine and clear cached factories (used by tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def set_engine(engine: AsyncEngine, **session_kwargs: Any) -> None:
    """Inject a pre-built engine and rebuild the session factory.

    Tests use this to point the application at an in-memory database.
    """
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession, **session_kwargs
    )
