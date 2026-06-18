"""Chatterbox TTS wrapper (MIT) — voice cloning + emotion, loaded on demand.

Powers the cloning flow: a reference sample conditions synthesis. Heavy imports
(``chatterbox``, ``torchaudio``) happen only in :meth:`_do_load`.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from hearsay_gpu.audio import floats_to_pcm16, pcm16_to_wav
from hearsay_gpu.config import get_gpu_settings
from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import TtsChunk, TtsModel

log = get_logger(__name__)


class ChatterboxModel(TtsModel):
    """On-demand Chatterbox model with reference-conditioned synthesis."""

    name = "chatterbox"

    def __init__(self) -> None:
        """Create the wrapper; the model is loaded on first use."""
        super().__init__()
        self._model: Any | None = None
        self._sample_rate = 24000

    def _do_load(self) -> None:  # pragma: no cover - requires chatterbox + GPU
        """Load Chatterbox onto the configured device."""
        from chatterbox.tts import ChatterboxTTS

        device = get_gpu_settings().device
        self._model = ChatterboxTTS.from_pretrained(device=device)
        self._sample_rate = int(self._model.sr)
        log.info("chatterbox loaded")

    def _reference_path(self, reference_pcm: bytes | None) -> str | None:
        """Write reference PCM to a temp WAV file and return its path."""
        if reference_pcm is None:
            return None
        wav = pcm16_to_wav(reference_pcm, sample_rate=16000)
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        Path(path).write_bytes(wav)
        return path

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        reference_pcm: bytes | None,
    ) -> Iterator[TtsChunk]:  # pragma: no cover - requires chatterbox + GPU
        """Synthesize ``text``, cloning the reference voice when provided."""
        self.load()
        assert self._model is not None
        ref_path = self._reference_path(reference_pcm)
        kwargs = {"audio_prompt_path": ref_path} if ref_path else {}
        wav = self._model.generate(text, **kwargs)
        samples = wav.squeeze().tolist()
        yield TtsChunk(pcm=floats_to_pcm16(samples), sample_rate=self._sample_rate)

    def make_embedding(self, reference_pcm: bytes) -> dict[str, Any]:
        """Produce persistable cloning metadata for a reference sample.

        Chatterbox conditions at synthesis time from the reference audio, so the
        durable artifact is the stored reference; we record its parameters.
        """
        return {
            "engine": "chatterbox",
            "reference_sample_rate": 16000,
            "reference_bytes": len(reference_pcm),
        }
