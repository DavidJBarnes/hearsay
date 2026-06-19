"""Fixtures for GPU daemon tests: fake model wrappers and a manager."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from hearsay_gpu.audio import floats_to_pcm16
from hearsay_gpu.config import GpuSettings
from hearsay_gpu.manager import ModelManager
from hearsay_gpu.models.base import Segment, SttModel, Transcription, TtsChunk, TtsModel


class FakeTts(TtsModel):
    """A deterministic TTS model emitting two short PCM chunks."""

    name = "kokoro"

    def __init__(self, sample_rate: int = 24000) -> None:
        super().__init__()
        self._sr = sample_rate
        self.last_reference: bytes | None = None

    def _do_load(self) -> None:
        self._loaded = True

    def synthesize(
        self, text: str, *, voice: str, speed: float, reference_pcm: bytes | None
    ) -> Iterator[TtsChunk]:
        self.load()
        self.last_reference = reference_pcm
        for _ in range(2):
            yield TtsChunk(pcm=floats_to_pcm16([0.1] * 100), sample_rate=self._sr)


class FakeCloneTts(FakeTts):
    """A TTS model that also supports cloning metadata."""

    name = "chatterbox"

    def make_embedding(self, reference_pcm: bytes) -> dict[str, Any]:
        return {"engine": "chatterbox", "reference_bytes": len(reference_pcm)}


class FakeStt(SttModel):
    """A deterministic STT model returning a fixed transcription."""

    name = "faster-whisper"

    def _do_load(self) -> None:
        self._loaded = True

    def transcribe(self, pcm16k: bytes, *, language: str | None) -> Transcription:
        self.load()
        return Transcription(
            text=f"heard {len(pcm16k)} bytes",
            language=language or "en",
            duration=1.0,
            segments=[Segment(start=0.0, end=1.0, text="heard")],
        )


class FakeVad:
    """A VAD stub: speech when any sample is non-zero."""

    def __init__(self) -> None:
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def speech_prob(self, window_pcm16: bytes, sample_rate: int) -> float:
        return 1.0 if any(window_pcm16) else 0.0


class FakeDiarizer:
    """A diarizer stub returning a single speaker turn."""

    def diarize(self, pcm16k: bytes) -> list[dict[str, Any]]:
        return [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]


@pytest.fixture
def settings() -> GpuSettings:
    """GPU settings with diarization disabled."""
    return GpuSettings(sample_rate=16000)


@pytest.fixture
def manager(settings: GpuSettings) -> ModelManager:
    """A manager wired with fake models."""
    return ModelManager(
        settings,
        tts_models={"kokoro": FakeTts(), "chatterbox": FakeCloneTts()},
        stt_models={"faster-whisper": FakeStt()},
        diarizer=FakeDiarizer(),  # type: ignore[arg-type]
        vad=FakeVad(),  # type: ignore[arg-type]
    )
