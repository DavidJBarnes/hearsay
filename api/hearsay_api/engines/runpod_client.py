"""RunPod engine client.

The interface is fully defined so the placement layer can route to RunPod
exactly as it routes to local. Per the v1 spec, one heavy engine target is
stubbed: every capability raises :class:`NotImplementedError` with a clear
message. This is the only permitted stub in the codebase.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from hearsay_api.engines.base import Engine, SynthesisResult, TranscriptionResult
from hearsay_api.logging import get_logger

log = get_logger(__name__)

_MESSAGE = (
    "RunPod engine '{name}' is not implemented in v1. Set HEARSAY_ENGINE_PLACEMENT "
    "to route '{name}' to 'local', or implement RunpodEngineClient against your "
    "RunPod serverless endpoint (HEARSAY_RUNPOD_ENDPOINT / HEARSAY_RUNPOD_API_KEY)."
)


class RunpodEngineClient(Engine):
    """An :class:`Engine` that would burst work to a RunPod endpoint.

    Fully wired into the registry and placement config; intentionally stubbed
    for v1. All methods raise :class:`NotImplementedError`.
    """

    def __init__(
        self,
        name: str,
        *,
        endpoint: str | None,
        api_key: str | None,
        supports_tts: bool = False,
        supports_stt: bool = False,
        supports_cloning: bool = False,
    ) -> None:
        """Record RunPod connection details and declared capabilities."""
        self.name = name
        self.endpoint = endpoint
        self.api_key = api_key
        self.supports_tts = supports_tts
        self.supports_stt = supports_stt
        self.supports_cloning = supports_cloning

    def _fail(self) -> NotImplementedError:
        """Return the standard not-implemented error for this engine."""
        return NotImplementedError(_MESSAGE.format(name=self.name))

    async def transcribe(
        self, audio: bytes, *, language: str | None = None, diarize: bool = False
    ) -> TranscriptionResult:
        """Not implemented in v1."""
        raise self._fail()

    async def transcribe_stream(
        self, frames: AsyncIterator[bytes], *, language: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Not implemented in v1."""
        raise self._fail()
        yield {}  # pragma: no cover

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> SynthesisResult:
        """Not implemented in v1."""
        raise self._fail()

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> AsyncIterator[bytes]:
        """Not implemented in v1."""
        raise self._fail()
        yield b""  # pragma: no cover

    async def clone_voice(self, reference_audio: bytes, *, name: str) -> dict[str, Any]:
        """Not implemented in v1."""
        raise self._fail()
