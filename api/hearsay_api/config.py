"""Application configuration via pydantic-settings.

All runtime configuration is environment-driven. The settings object is the
single source of truth for engine placement, model identifiers, database and
storage credentials, and feature toggles (diarization, RunPod).
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnginePlacement(StrEnum):
    """Where an engine's work is executed."""

    LOCAL = "local"
    RUNPOD = "runpod"


class StorageBackendKind(StrEnum):
    """Selectable storage backends."""

    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    """Typed application settings loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="HEARSAY_",
        env_file=".env",
        extra="ignore",
    )

    # --- Service ---
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Database ---
    database_url: str = "postgresql+asyncpg://hearsay:hearsay@postgres:5432/hearsay"

    # --- GPU daemon ---
    gpu_base_url: str = "http://gpu:8001"
    gpu_request_timeout_s: float = 600.0

    # --- Engine placement (engine name -> "local" | "runpod") ---
    engine_placement: dict[str, EnginePlacement] = Field(
        default_factory=lambda: {
            "kokoro": EnginePlacement.LOCAL,
            "chatterbox": EnginePlacement.LOCAL,
            "faster-whisper": EnginePlacement.LOCAL,
            "pyannote": EnginePlacement.LOCAL,
        }
    )

    # --- Model identifiers ---
    whisper_model: str = "large-v3"
    whisper_compute_type: str = "float16"
    kokoro_default_voice: str = "af_heart"
    cuda_device: str = "cuda"

    # --- Diarization (gated, OFF by default) ---
    diarization_enabled: bool = False
    hf_token: str | None = None

    # --- RunPod (present but unused in v1) ---
    runpod_endpoint: str | None = None
    runpod_api_key: str | None = None
    runpod_stubbed_engine: str = "chatterbox"

    # --- Storage ---
    storage_backend: StorageBackendKind = StorageBackendKind.LOCAL
    storage_local_root: str = "/data/hearsay"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "hearsay"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # --- Auth bootstrap ---
    bootstrap_api_key: str | None = None

    # --- Queue worker ---
    worker_enabled: bool = True
    worker_poll_interval_s: float = 1.0

    # --- Realtime / audio ---
    realtime_sample_rate: int = 16000
    vad_aggressiveness: int = 2

    @field_validator("engine_placement", mode="before")
    @classmethod
    def _parse_placement(cls, value: object) -> object:
        """Allow the placement map to be provided as a JSON string in env."""
        if isinstance(value, str):
            return json.loads(value)
        return value

    def placement_for(self, engine_name: str) -> EnginePlacement:
        """Return the configured placement for ``engine_name`` (default local)."""
        return self.engine_placement.get(engine_name, EnginePlacement.LOCAL)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()


# Re-exported literal of supported response formats for OpenAI compatibility.
ResponseFormat = Literal["wav", "mp3", "opus", "flac", "pcm"]
