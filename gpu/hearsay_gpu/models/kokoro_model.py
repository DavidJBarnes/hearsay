"""Kokoro TTS wrapper (default voice engine, < 1 GB, warm).

Kokoro produces 24 kHz float audio. We convert to int16 PCM chunks suitable for
streaming. Heavy imports (``kokoro``, ``numpy``) happen only in :meth:`_do_load`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from hearsay_gpu.audio import floats_to_pcm16
from hearsay_gpu.config import get_gpu_settings
from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import TtsChunk, TtsModel

log = get_logger(__name__)

KOKORO_SAMPLE_RATE = 24000


class KokoroModel(TtsModel):
    """Warm Kokoro pipeline producing streaming PCM chunks."""

    name = "kokoro"

    def __init__(self) -> None:
        """Create the wrapper; the pipeline is loaded lazily."""
        super().__init__()
        self._pipeline: Any | None = None

    def _do_load(self) -> None:  # pragma: no cover - requires kokoro + GPU
        """Instantiate the Kokoro pipeline on the configured device."""
        from kokoro import KPipeline

        self._pipeline = KPipeline(lang_code="a")
        log.info("kokoro loaded")

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        reference_pcm: bytes | None,
    ) -> Iterator[TtsChunk]:  # pragma: no cover - requires kokoro + GPU
        """Yield PCM chunks for ``text`` using a preset Kokoro ``voice``."""
        self.load()
        assert self._pipeline is not None
        chosen = voice or get_gpu_settings().kokoro_default_voice
        for _, _, audio in self._pipeline(text, voice=chosen, speed=speed):
            samples = audio.tolist() if hasattr(audio, "tolist") else list(audio)
            yield TtsChunk(pcm=floats_to_pcm16(samples), sample_rate=KOKORO_SAMPLE_RATE)
