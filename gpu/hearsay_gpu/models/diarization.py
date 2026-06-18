"""pyannote diarization wrapper (gated, OFF by default).

Wired and selectable but disabled unless ``HEARSAY_GPU_DIARIZATION_ENABLED`` is
true and an HF token is supplied. Heavy imports happen only in :meth:`_do_load`.
"""

from __future__ import annotations

from typing import Any

from hearsay_gpu.audio import pcm16_to_wav
from hearsay_gpu.config import get_gpu_settings
from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import ModelWrapper

log = get_logger(__name__)


class DiarizationUnavailableError(RuntimeError):
    """Raised when diarization is requested but not enabled/configured."""


class Diarizer(ModelWrapper):
    """Warm pyannote diarization pipeline (only when enabled)."""

    name = "pyannote"

    def __init__(self) -> None:
        """Create the wrapper; the pipeline is loaded lazily when enabled."""
        super().__init__()
        self._pipeline: Any | None = None

    def _check_enabled(self) -> None:
        """Raise if diarization is disabled or missing an HF token."""
        settings = get_gpu_settings()
        if not settings.diarization_enabled:
            raise DiarizationUnavailableError(
                "diarization is disabled; set HEARSAY_GPU_DIARIZATION_ENABLED=true"
            )
        if not settings.hf_token:
            raise DiarizationUnavailableError(
                "diarization requires HEARSAY_GPU_HF_TOKEN to be set"
            )

    def _do_load(self) -> None:  # pragma: no cover - requires pyannote + HF token
        """Load the pyannote speaker-diarization pipeline."""
        from pyannote.audio import Pipeline

        settings = get_gpu_settings()
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=settings.hf_token
        )
        log.info("pyannote diarization loaded")

    def diarize(self, pcm16k: bytes) -> list[dict[str, Any]]:
        """Return speaker turns for the given 16 kHz PCM audio."""
        self._check_enabled()
        return self._run(pcm16k)

    def _run(
        self, pcm16k: bytes
    ) -> list[dict[str, Any]]:  # pragma: no cover - real model
        """Execute the pipeline and normalize its output to dicts."""
        import io

        self.load()
        assert self._pipeline is not None
        wav = pcm16_to_wav(pcm16k, sample_rate=16000)
        diarization = self._pipeline(io.BytesIO(wav))
        turns: list[dict[str, Any]] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append({"start": turn.start, "end": turn.end, "speaker": speaker})
        return turns
