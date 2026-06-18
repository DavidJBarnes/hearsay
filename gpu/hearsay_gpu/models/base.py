"""Model wrapper interfaces.

Each wrapper owns a single warm model and exposes a narrow, typed surface. The
manager loads them lazily and keeps them resident. Wrappers import heavy ML
libraries only inside :meth:`load`, so the modules import cleanly without GPU
dependencies present (e.g. during unit tests).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TtsChunk:
    """A chunk of synthesized int16 PCM at ``sample_rate``."""

    pcm: bytes
    sample_rate: int


@dataclass(slots=True)
class Segment:
    """A transcript segment with timing and optional speaker."""

    start: float
    end: float
    text: str
    speaker: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data: dict[str, Any] = {"start": self.start, "end": self.end, "text": self.text}
        if self.speaker is not None:
            data["speaker"] = self.speaker
        return data


@dataclass(slots=True)
class Transcription:
    """A full transcription result."""

    text: str
    language: str | None = None
    duration: float | None = None
    segments: list[Segment] = field(default_factory=list)


class ModelWrapper(ABC):
    """Base class for a lazily-loaded warm model."""

    name: str = "model"

    def __init__(self) -> None:
        """Create the wrapper without loading the underlying model."""
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return whether the model has been loaded into memory."""
        return self._loaded

    @abstractmethod
    def _do_load(self) -> None:
        """Load the underlying model (heavy imports happen here)."""

    def load(self) -> None:
        """Idempotently load the model."""
        if not self._loaded:
            self._do_load()
            self._loaded = True


class TtsModel(ModelWrapper):
    """A text-to-speech model wrapper."""

    @abstractmethod
    def synthesize(
        self, text: str, *, voice: str, speed: float, reference_pcm: bytes | None
    ) -> Iterator[TtsChunk]:
        """Yield PCM chunks for ``text`` in the requested ``voice``."""


class SttModel(ModelWrapper):
    """A speech-to-text model wrapper."""

    @abstractmethod
    def transcribe(self, pcm16k: bytes, *, language: str | None) -> Transcription:
        """Transcribe 16 kHz mono int16 PCM."""
