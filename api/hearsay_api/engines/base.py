"""Core engine interface, result types, and registry.

An :class:`Engine` is a uniform front for a speech model regardless of where it
runs. Concrete engines either proxy to the local GPU daemon
(:class:`~hearsay_api.engines.local_client.LocalEngineClient`) or to RunPod
(:class:`~hearsay_api.engines.runpod_client.RunpodEngineClient`).
"""

from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


class EngineError(Exception):
    """An engine call failed; carries an HTTP status and a client-safe detail.

    Lets the local/runpod clients translate upstream failures (a 5xx from the
    GPU daemon, an unreachable daemon) into a response that preserves the real
    cause instead of collapsing to an opaque ``500 Internal Server Error``.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        """Store the HTTP status to return and the detail message."""
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class TranscriptionResult:
    """Result of a (non-streaming) transcription."""

    text: str
    language: str | None = None
    duration: float | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)
    diarization: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class SynthesisResult:
    """Result of a (non-streaming) synthesis."""

    audio: bytes
    format: str
    sample_rate: int
    duration_s: float


class Engine(ABC):
    """Uniform interface implemented by every speech engine.

    Engines declare which capabilities they support via the boolean class
    attributes. Calling an unsupported method raises ``NotImplementedError``
    from the default implementation.
    """

    name: str = "engine"
    supports_tts: bool = False
    supports_stt: bool = False
    supports_cloning: bool = False

    async def transcribe(
        self, audio: bytes, *, language: str | None = None, diarize: bool = False
    ) -> TranscriptionResult:
        """Transcribe a complete audio buffer to text."""
        raise NotImplementedError(f"{self.name} does not support transcription")

    async def transcribe_stream(
        self, frames: AsyncIterator[bytes], *, language: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield incremental transcript events for a live frame stream."""
        raise NotImplementedError(f"{self.name} does not support streaming STT")
        yield {}  # pragma: no cover - makes this an async generator

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> SynthesisResult:
        """Synthesize ``text`` into a complete audio buffer."""
        raise NotImplementedError(f"{self.name} does not support synthesis")

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield audio frames as they are generated."""
        raise NotImplementedError(f"{self.name} does not support streaming synthesis")
        yield b""  # pragma: no cover - makes this an async generator

    async def clone_voice(self, reference_audio: bytes, *, name: str) -> dict[str, Any]:
        """Prepare a cloned voice from a reference sample.

        Returns metadata to persist with the voice (e.g. embedding ref).
        """
        raise NotImplementedError(f"{self.name} does not support voice cloning")


class EngineRegistry:
    """A name-keyed collection of engine instances."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._engines: dict[str, Engine] = {}

    def register(self, engine: Engine) -> None:
        """Register ``engine`` under its ``name`` (replacing any existing)."""
        self._engines[engine.name] = engine

    def get(self, name: str) -> Engine:
        """Return the engine registered under ``name``.

        Raises ``KeyError`` with the available names if not found.
        """
        try:
            return self._engines[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._engines)) or "(none)"
            raise KeyError(f"unknown engine '{name}'; registered engines: {available}") from exc

    def names(self) -> list[str]:
        """Return the sorted list of registered engine names."""
        return sorted(self._engines)

    def __contains__(self, name: object) -> bool:
        """Return whether ``name`` is a registered engine."""
        return name in self._engines
