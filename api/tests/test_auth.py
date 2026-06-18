"""Tests for API-key authentication."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from hearsay_api import auth, db
from hearsay_api.config import Settings
from hearsay_api.models import ApiKey


def test_hash_and_generate() -> None:
    """Hashing is deterministic and generated keys are prefixed."""
    assert auth.hash_key("abc") == auth.hash_key("abc")
    assert auth.generate_key().startswith("sk-hearsay-")


def test_extract_token_valid() -> None:
    """A well-formed bearer header yields the token."""
    assert auth._extract_token("Bearer xyz") == "xyz"


def test_extract_token_invalid() -> None:
    """Missing or malformed headers raise 401."""
    for header in (None, "Token abc", ""):
        with pytest.raises(HTTPException) as exc:
            auth._extract_token(header)
        assert exc.value.status_code == 401


async def test_ensure_bootstrap_key(engine_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bootstrap key is provisioned once and not duplicated."""
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(bootstrap_api_key="sk-boot"))
    async with db.get_sessionmaker()() as session:
        await auth.ensure_bootstrap_key(session)
        await auth.ensure_bootstrap_key(session)  # idempotent
    async with db.get_sessionmaker()() as session:
        rows = (await session.scalars(select(ApiKey))).all()
    assert len(rows) == 1


async def test_ensure_bootstrap_key_disabled(
    engine_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No key is created when none is configured."""
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(bootstrap_api_key=None))
    async with db.get_sessionmaker()() as session:
        await auth.ensure_bootstrap_key(session)
        count = await session.scalar(select(func.count()).select_from(ApiKey))
    assert count == 0


async def test_require_api_key_valid(engine_db: None) -> None:
    """A valid token authenticates and updates last_used_at."""
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=auth.hash_key("good"), name="t"))
        await session.commit()
    async with db.get_sessionmaker()() as session:
        key = await auth.require_api_key("Bearer good", session)
        assert key.name == "t"
        assert key.last_used_at is not None


async def test_require_api_key_invalid(engine_db: None) -> None:
    """An unknown token is rejected with 401."""
    async with db.get_sessionmaker()() as session:
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key("Bearer nope", session)
    assert exc.value.status_code == 401
