"""GPU daemon configuration (pydantic-settings, env-driven)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GpuSettings(BaseSettings):
    """Typed settings for the warm-model daemon."""

    model_config = SettingsConfigDict(
        env_prefix="HEARSAY_GPU_", env_file=".env", extra="ignore"
    )

    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8001

    device: str = "cuda"
    compute_type: str = "float16"

    # Model identifiers / preload toggles.
    whisper_model: str = "large-v3"
    preload_whisper: bool = True
    preload_kokoro: bool = True
    preload_chatterbox: bool = False  # loaded on demand

    kokoro_default_voice: str = "af_heart"

    # Diarization (gated, OFF by default).
    diarization_enabled: bool = False
    hf_token: str | None = None

    # Realtime / VAD.
    sample_rate: int = 16000
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 500
    vad_window_ms: int = 32


@lru_cache
def get_gpu_settings() -> GpuSettings:
    """Return the cached GPU settings instance."""
    return GpuSettings()
