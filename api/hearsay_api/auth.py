"""API-key authentication for ``/v1/*`` routes.

Keys are presented as ``Authorization: Bearer <key>`` and stored only as
SHA-256 hashes. A bootstrap key from settings is auto-provisioned on startup so
the service is usable out of the box.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hearsay_api.config import get_settings
from hearsay_api.db import get_session
from hearsay_api.logging import get_logger
from hearsay_api.models import ApiKey, _now

log = get_logger(__name__)


def hash_key(raw_key: str) -> str:
    """Return the hex SHA-256 of ``raw_key``."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    """Generate a new random API key string."""
    return "sk-hearsay-" + secrets.token_urlsafe(32)


async def ensure_bootstrap_key(session: AsyncSession) -> None:
    """Provision the configured bootstrap key if it isn't present yet."""
    raw = get_settings().bootstrap_api_key
    if not raw:
        return
    key_hash = hash_key(raw)
    existing = await session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if existing is None:
        session.add(ApiKey(key_hash=key_hash, name="bootstrap"))
        await session.commit()
        log.info("provisioned bootstrap api key")


def _extract_token(authorization: str | None) -> str:
    """Pull the bearer token from an ``Authorization`` header or raise 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:].strip()


async def require_api_key(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    """FastAPI dependency that authenticates the bearer token.

    On success the key's ``last_used_at`` is refreshed and the row returned.
    """
    token = _extract_token(authorization)
    key_hash = hash_key(token)
    api_key = await session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await session.execute(update(ApiKey).where(ApiKey.id == api_key.id).values(last_used_at=_now()))
    await session.commit()
    return api_key
