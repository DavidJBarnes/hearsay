"""Pydantic v2 request/response schemas for the API surface.

These define the public contract for both the OpenAI-compatible and native
endpoints. ORM rows are converted to these models before serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- OpenAI-compatible TTS ---------------------------------------------------


class SpeechRequest(BaseModel):
    """Body of ``POST /v1/audio/speech`` (OpenAI ``audio/speech`` shape)."""

    model: str = "kokoro"
    input: str = Field(min_length=1)
    voice: str = "af_heart"
    response_format: Literal["wav", "mp3", "opus", "flac", "pcm"] = "wav"
    speed: float = Field(default=1.0, gt=0, le=4.0)
    stream: bool = False


# --- OpenAI-compatible STT ---------------------------------------------------


class TranscriptionSegment(BaseModel):
    """A single timestamped transcript segment."""

    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptionResponse(BaseModel):
    """Body of the transcription response (OpenAI ``verbose_json`` subset)."""

    text: str
    language: str | None = None
    duration: float | None = None
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    diarization: list[dict[str, Any]] | None = None


# --- Voices ------------------------------------------------------------------


class VoiceCreate(BaseModel):
    """Form fields accepted when creating a voice."""

    name: str = Field(min_length=1, max_length=255)
    engine: str = "chatterbox"


class VoiceOut(BaseModel):
    """A voice as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    engine: str
    type: str
    reference_audio_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="voice_metadata")
    created_at: datetime


# --- Jobs --------------------------------------------------------------------


class JobCreate(BaseModel):
    """Body of ``POST /v1/jobs`` for batch TTS/STT."""

    type: Literal["tts", "stt"]
    engine: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    input_ref: str | None = None


class JobOut(BaseModel):
    """A job row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    status: str
    engine: str
    params: dict[str, Any]
    input_ref: str | None
    output_ref: str | None
    error: str | None
    timing: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# --- Realtime ----------------------------------------------------------------


class RealtimeMessage(BaseModel):
    """A message emitted over the realtime STT WebSocket."""

    type: Literal["partial", "final", "ready", "error"]
    text: str = ""
    start: float | None = None
    end: float | None = None
    language: str | None = None
