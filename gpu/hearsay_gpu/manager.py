"""Model manager: owns warm models and exposes serializable operations.

The HTTP/WS layer is thin; all model orchestration lives here. Models are
injected (so tests use fakes) or default to the real wrappers. Outputs are
plain bytes/dicts ready for transport.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from hearsay_gpu.audio import encode
from hearsay_gpu.config import GpuSettings, get_gpu_settings
from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import SttModel, Transcription, TtsModel
from hearsay_gpu.models.chatterbox_model import ChatterboxModel
from hearsay_gpu.models.diarization import Diarizer
from hearsay_gpu.models.kokoro_model import KokoroModel
from hearsay_gpu.models.vad import SileroVad
from hearsay_gpu.models.whisper_model import WhisperModel

log = get_logger(__name__)


class ModelManager:
    """Holds the warm models and runs synthesis/transcription/diarization."""

    def __init__(
        self,
        settings: GpuSettings | None = None,
        *,
        tts_models: dict[str, TtsModel] | None = None,
        stt_models: dict[str, SttModel] | None = None,
        diarizer: Diarizer | None = None,
        vad: SileroVad | None = None,
    ) -> None:
        """Create the manager, defaulting to the real model wrappers."""
        self.settings = settings or get_gpu_settings()
        self._tts: dict[str, TtsModel] = tts_models or {
            "kokoro": KokoroModel(),
            "chatterbox": ChatterboxModel(),
        }
        self._stt: dict[str, SttModel] = stt_models or {
            "faster-whisper": WhisperModel()
        }
        self.diarizer = diarizer or Diarizer()
        self.vad = vad or SileroVad()

    def get_tts(self, engine: str) -> TtsModel:
        """Return the TTS model wrapper for ``engine`` or raise ``KeyError``."""
        if engine not in self._tts:
            raise KeyError(f"unknown tts engine: {engine}")
        return self._tts[engine]

    def get_stt(self, engine: str) -> SttModel:
        """Return the STT model wrapper for ``engine`` or raise ``KeyError``."""
        if engine not in self._stt:
            raise KeyError(f"unknown stt engine: {engine}")
        return self._stt[engine]

    def preload(self) -> None:  # pragma: no cover - exercised with real models
        """Warm up models selected for preloading at startup."""
        if self.settings.preload_kokoro:
            self._tts["kokoro"].load()
        if self.settings.preload_whisper:
            self._stt["faster-whisper"].load()
        if self.settings.preload_chatterbox:
            self._tts["chatterbox"].load()

    def synthesize(
        self,
        *,
        engine: str,
        text: str,
        voice: str,
        speed: float,
        response_format: str,
        reference_pcm: bytes | None,
    ) -> dict[str, Any]:
        """Synthesize ``text`` and return encoded audio plus metadata."""
        model = self.get_tts(engine)
        pcm = bytearray()
        sample_rate = self.settings.sample_rate
        for chunk in model.synthesize(
            text, voice=voice, speed=speed, reference_pcm=reference_pcm
        ):
            pcm.extend(chunk.pcm)
            sample_rate = chunk.sample_rate
        audio = encode(bytes(pcm), sample_rate=sample_rate, out_format=response_format)
        duration_s = len(pcm) / (sample_rate * 2) if sample_rate else 0.0
        return {
            "audio": audio,
            "format": response_format,
            "sample_rate": sample_rate,
            "duration_s": duration_s,
        }

    def synthesize_stream(
        self,
        *,
        engine: str,
        text: str,
        voice: str,
        speed: float,
        reference_pcm: bytes | None,
    ) -> Iterator[bytes]:
        """Yield raw int16 PCM frames as they are synthesized (streaming path)."""
        model = self.get_tts(engine)
        for chunk in model.synthesize(
            text, voice=voice, speed=speed, reference_pcm=reference_pcm
        ):
            yield chunk.pcm

    def transcribe(
        self, *, engine: str, pcm16k: bytes, language: str | None, diarize: bool
    ) -> dict[str, Any]:
        """Transcribe PCM and optionally attach diarization turns."""
        model = self.get_stt(engine)
        result: Transcription = model.transcribe(pcm16k, language=language)
        payload: dict[str, Any] = {
            "text": result.text,
            "language": result.language,
            "duration": result.duration,
            "segments": [s.as_dict() for s in result.segments],
            "diarization": None,
        }
        if diarize:
            payload["diarization"] = self.diarizer.diarize(pcm16k)
        return payload

    def clone_voice(
        self, *, engine: str, name: str, reference_pcm: bytes
    ) -> dict[str, Any]:
        """Produce cloning metadata for a reference sample."""
        model = self.get_tts(engine)
        make_embedding = getattr(model, "make_embedding", None)
        if make_embedding is None:
            raise KeyError(f"engine '{engine}' does not support cloning")
        meta: dict[str, Any] = make_embedding(reference_pcm)
        meta["name"] = name
        return meta
