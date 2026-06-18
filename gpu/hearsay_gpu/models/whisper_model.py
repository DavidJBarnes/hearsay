"""faster-whisper (CTranslate2) STT wrapper — warm, FP16 large-v3 by default.

Compute type and model size are configurable (e.g. ``large-v3-turbo`` / INT8).
Heavy imports (``faster_whisper``, ``numpy``) happen only in :meth:`_do_load`.
"""

from __future__ import annotations

from typing import Any

from hearsay_gpu.config import get_gpu_settings
from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import Segment, SttModel, Transcription

log = get_logger(__name__)


def pcm16_to_float32(pcm16k: bytes) -> Any:  # pragma: no cover - requires numpy
    """Convert int16 PCM bytes to a float32 numpy array in [-1, 1]."""
    import numpy as np

    ints = np.frombuffer(pcm16k, dtype=np.int16)
    return ints.astype(np.float32) / 32768.0


class WhisperModel(SttModel):
    """Warm faster-whisper model."""

    name = "faster-whisper"

    def __init__(self) -> None:
        """Create the wrapper; the model is loaded lazily."""
        super().__init__()
        self._model: Any | None = None

    def _do_load(self) -> None:  # pragma: no cover - requires faster_whisper + GPU
        """Load the CTranslate2 model with the configured compute type."""
        from faster_whisper import WhisperModel as FWModel

        settings = get_gpu_settings()
        self._model = FWModel(
            settings.whisper_model,
            device=settings.device,
            compute_type=settings.compute_type,
        )
        log.info(
            "faster-whisper loaded", extra={"extra": {"model": settings.whisper_model}}
        )

    def transcribe(
        self, pcm16k: bytes, *, language: str | None
    ) -> Transcription:  # pragma: no cover - requires faster_whisper + GPU
        """Transcribe 16 kHz mono PCM into a :class:`Transcription`."""
        self.load()
        assert self._model is not None
        audio = pcm16_to_float32(pcm16k)
        segments_iter, info = self._model.transcribe(audio, language=language)
        segments = [
            Segment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments_iter
        ]
        text = " ".join(s.text for s in segments).strip()
        return Transcription(
            text=text,
            language=getattr(info, "language", language),
            duration=getattr(info, "duration", None),
            segments=segments,
        )
