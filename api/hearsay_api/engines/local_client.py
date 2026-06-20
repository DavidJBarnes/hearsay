"""Local engine client: proxies to the warm GPU daemon over HTTP/WebSocket.

A single :class:`LocalEngineClient` is instantiated per logical engine name
(``kokoro``, ``chatterbox``, ``faster-whisper``). It forwards calls to the GPU
daemon, which keeps the underlying models resident in VRAM.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import Any

import httpx

from hearsay_api.engines.base import (
    Engine,
    EngineError,
    SynthesisResult,
    TranscriptionResult,
)
from hearsay_api.logging import get_logger

log = get_logger(__name__)


def _upstream_detail(response: httpx.Response) -> str:
    """Extract the daemon's error ``detail`` from a failed response body."""
    fallback = response.text or response.reason_phrase
    try:
        body = response.json()
    except ValueError:
        return fallback
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])
    return fallback


def _engine_error(name: str, exc: httpx.HTTPError) -> EngineError:
    """Convert an httpx failure into an :class:`EngineError` for the gateway."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail = _upstream_detail(exc.response)
        # Forward client errors verbatim; report upstream 5xx as a bad gateway.
        status = exc.response.status_code if exc.response.status_code < 500 else 502
        return EngineError(status, f"engine '{name}': {detail}")
    return EngineError(502, f"engine '{name}' unreachable: {exc}")


class LocalEngineClient(Engine):
    """An :class:`Engine` backed by the local GPU daemon."""

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        timeout_s: float,
        supports_tts: bool = False,
        supports_stt: bool = False,
        supports_cloning: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the client for one engine served by the daemon."""
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.supports_tts = supports_tts
        self.supports_stt = supports_stt
        self.supports_cloning = supports_cloning
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to the daemon and return the decoded JSON response."""
        try:
            resp = await self._client.post(f"{self.base_url}{path}", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise _engine_error(self.name, exc) from exc
        data: dict[str, Any] = resp.json()
        return data

    async def transcribe(
        self, audio: bytes, *, language: str | None = None, diarize: bool = False
    ) -> TranscriptionResult:
        """Forward a full-buffer transcription request to the daemon."""
        data = await self._post(
            "/transcribe",
            {
                "engine": self.name,
                "audio_b64": base64.b64encode(audio).decode("ascii"),
                "language": language,
                "diarize": diarize,
            },
        )
        return TranscriptionResult(
            text=data["text"],
            language=data.get("language"),
            duration=data.get("duration"),
            segments=data.get("segments", []),
            diarization=data.get("diarization"),
        )

    async def transcribe_stream(
        self, frames: AsyncIterator[bytes], *, language: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream PCM frames to the daemon WS and yield transcript events."""
        ws_url = self.base_url.replace("http", "ws", 1) + "/transcribe_stream"
        async for event in _ws_transcribe(ws_url, frames, language):
            yield event

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> SynthesisResult:
        """Forward a full synthesis request to the daemon."""
        payload: dict[str, Any] = {
            "engine": self.name,
            "text": text,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        if reference_audio is not None:
            payload["reference_audio_b64"] = base64.b64encode(reference_audio).decode("ascii")
        data = await self._post("/synthesize", payload)
        return SynthesisResult(
            audio=base64.b64decode(data["audio_b64"]),
            format=data["format"],
            sample_rate=data["sample_rate"],
            duration_s=data["duration_s"],
        )

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio frames from the daemon."""
        payload: dict[str, Any] = {
            "engine": self.name,
            "text": text,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        if reference_audio is not None:
            payload["reference_audio_b64"] = base64.b64encode(reference_audio).decode("ascii")
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/synthesize_stream", json=payload
            ) as resp:
                if resp.is_error:
                    await resp.aread()
                    resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.HTTPError as exc:
            raise _engine_error(self.name, exc) from exc

    async def clone_voice(self, reference_audio: bytes, *, name: str) -> dict[str, Any]:
        """Forward a voice-cloning request to the daemon."""
        return await self._post(
            "/clone_voice",
            {
                "engine": self.name,
                "name": name,
                "reference_audio_b64": base64.b64encode(reference_audio).decode("ascii"),
            },
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


async def _ws_transcribe(
    ws_url: str, frames: AsyncIterator[bytes], language: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Open a WS to the daemon, pump frames, and yield JSON transcript events."""
    import asyncio
    import contextlib
    import json as _json

    import websockets

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(_json.dumps({"type": "config", "language": language}))

        async def _pump() -> None:
            async for frame in frames:
                await ws.send(frame)
            await ws.send(_json.dumps({"type": "eof"}))

        pump_task = asyncio.create_task(_pump())
        try:
            async for message in ws:
                event = _json.loads(message)
                yield event
                if event.get("type") == "final" and event.get("eof"):
                    break
        finally:
            # Cancel and await the pump so the task and its frame iterator are
            # fully torn down each session (otherwise they leak across sessions).
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task
