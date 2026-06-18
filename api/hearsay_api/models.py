"""SQLAlchemy ORM models for Hearsay.

These map directly to the tables created by the Alembic migrations. No schema
is created outside of migrations; the models exist for typed query access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# JSONB on PostgreSQL (production), plain JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    """Return a new string UUID used as a primary key."""
    return str(uuid.uuid4())


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


from hearsay_api.db import Base  # noqa: E402  (Base import after helpers for clarity)


class ApiKey(Base):
    """An API key permitted to access ``/v1/*`` routes."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Voice(Base):
    """A preset or cloned voice usable for synthesis."""

    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    engine: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))  # preset | cloned
    reference_audio_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    voice_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    """A queued TTS or STT job tracked through its lifecycle."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(8))  # tts | stt
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    engine: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    input_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    timing: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    transcript: Mapped[Transcript | None] = relationship(back_populates="job", uselist=False)


class Transcript(Base):
    """The text result of an STT job, with segment and diarization detail."""

    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    diarization: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job] = relationship(back_populates="transcript")


class AudioArtifact(Base):
    """Metadata about a stored audio blob (input or output)."""

    __tablename__ = "audio_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32))  # input | output | reference
    ref: Mapped[str] = mapped_column(String(512))
    format: Mapped[str] = mapped_column(String(16))
    duration_s: Mapped[float | None] = mapped_column(nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
