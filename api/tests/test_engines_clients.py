"""Tests for LocalEngineClient (HTTP + WS) and the placement factory."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hearsay_api.config import EnginePlacement, Settings
from hearsay_api.engines.local_client import LocalEngineClient, _ws_transcribe
from hearsay_api.engines.local_client import LocalEngineClient as _LC
from hearsay_api.engines.placement import (
    build_registry,
    resolve_engine_name,
)
from hearsay_api.engines.runpod_client import RunpodEngineClient


def _mock_client(handler: Any) -> httpx.AsyncClient:
    """Build an httpx client backed by a mock transport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_local_transcribe() -> None:
    """transcribe() posts to /transcribe and parses the response."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        payload = json.loads(request.content)
        assert payload["engine"] == "faster-whisper"
        return httpx.Response(
            200,
            json={
                "text": "hi",
                "language": "en",
                "duration": 2.0,
                "segments": [{"start": 0, "end": 1, "text": "hi"}],
                "diarization": None,
            },
        )

    client = LocalEngineClient(
        "faster-whisper", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    result = await client.transcribe(b"audio", language="en")
    assert result.text == "hi"
    assert result.duration == 2.0
    await client.aclose()


async def test_local_synthesize_with_reference() -> None:
    """synthesize() includes reference audio and decodes audio bytes."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["reference_audio_b64"] == base64.b64encode(b"ref").decode()
        return httpx.Response(
            200,
            json={
                "audio_b64": base64.b64encode(b"wavbytes").decode(),
                "format": "wav",
                "sample_rate": 24000,
                "duration_s": 1.0,
            },
        )

    client = LocalEngineClient(
        "chatterbox", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    result = await client.synthesize("hi", voice="v", reference_audio=b"ref")
    assert result.audio == b"wavbytes"
    assert result.sample_rate == 24000


async def test_local_synthesize_no_reference() -> None:
    """synthesize() omits reference audio when none is given."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "reference_audio_b64" not in payload
        return httpx.Response(
            200,
            json={
                "audio_b64": base64.b64encode(b"x").decode(),
                "format": "wav",
                "sample_rate": 24000,
                "duration_s": 1.0,
            },
        )

    client = LocalEngineClient(
        "kokoro", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    result = await client.synthesize("hi", voice="v")
    assert result.audio == b"x"


async def test_local_synthesize_stream() -> None:
    """synthesize_stream() yields chunked bytes, with reference passed through."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/synthesize_stream"
        payload = json.loads(request.content)
        assert payload["reference_audio_b64"] == base64.b64encode(b"ref").decode()
        return httpx.Response(200, content=b"abc")

    client = LocalEngineClient(
        "kokoro", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    chunks = [c async for c in client.synthesize_stream("hi", voice="v", reference_audio=b"ref")]
    assert b"".join(chunks) == b"abc"


async def test_local_synthesize_stream_no_reference() -> None:
    """synthesize_stream() works without a reference (false branch)."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "reference_audio_b64" not in payload
        return httpx.Response(200, content=b"z")

    client = LocalEngineClient(
        "kokoro", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    chunks = [c async for c in client.synthesize_stream("hi", voice="v")]
    assert b"".join(chunks) == b"z"


async def test_local_clone_voice() -> None:
    """clone_voice() posts the reference and returns metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"engine": "chatterbox", "ok": True})

    client = LocalEngineClient(
        "chatterbox", base_url="http://gpu", timeout_s=5, client=_mock_client(handler)
    )
    meta = await client.clone_voice(b"ref", name="bob")
    assert meta["ok"] is True


# --- WebSocket streaming -----------------------------------------------------


class FakeWebSocket:
    """A fake websockets connection yielding canned server messages."""

    def __init__(self, messages: list[str]) -> None:
        self.sent: list[Any] = []
        self._messages = messages

    async def __aenter__(self) -> FakeWebSocket:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def send(self, data: Any) -> None:
        self.sent.append(data)

    def __aiter__(self) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            import asyncio

            for m in self._messages:
                await asyncio.sleep(0)  # yield control so the pump task runs
                yield m

        return _gen()


async def test_ws_transcribe(monkeypatch: pytest.MonkeyPatch) -> None:
    """_ws_transcribe pumps frames and yields parsed events until final eof."""
    messages = [
        json.dumps({"type": "partial", "text": "p"}),
        json.dumps({"type": "final", "text": "f", "eof": True}),
        json.dumps({"type": "partial", "text": "ignored"}),
    ]
    fake = FakeWebSocket(messages)

    monkeypatch.setattr("websockets.connect", lambda *a, **k: fake, raising=False)

    async def frames() -> AsyncIterator[bytes]:
        yield b"f1"
        yield b"f2"

    events = [e async for e in _ws_transcribe("ws://gpu/transcribe_stream", frames(), "en")]
    assert events[0]["text"] == "p"
    assert events[1]["eof"] is True
    assert len(events) == 2  # stops after final+eof
    assert json.dumps({"type": "eof"}) in fake.sent  # pump forwarded EOF
    assert b"f1" in fake.sent and b"f2" in fake.sent  # pump forwarded frames


async def test_ws_transcribe_natural_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """The WS loop ends when the server closes without a final+eof marker."""
    messages = [json.dumps({"type": "partial", "text": "a"})]
    fake = FakeWebSocket(messages)
    monkeypatch.setattr("websockets.connect", lambda *a, **k: fake, raising=False)

    async def frames() -> AsyncIterator[bytes]:
        yield b"f"

    events = [e async for e in _ws_transcribe("ws://gpu/x", frames(), None)]
    assert events == [{"type": "partial", "text": "a"}]


async def test_local_transcribe_stream_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """transcribe_stream builds the ws url and delegates to _ws_transcribe."""

    async def fake_ws(url: str, frames: Any, language: str | None) -> AsyncIterator[dict]:
        assert url == "ws://gpu/transcribe_stream"
        yield {"type": "final", "text": "ok"}

    monkeypatch.setattr("hearsay_api.engines.local_client._ws_transcribe", fake_ws)
    client = LocalEngineClient("faster-whisper", base_url="http://gpu", timeout_s=5)

    async def frames() -> AsyncIterator[bytes]:
        yield b"x"

    events = [e async for e in client.transcribe_stream(frames(), language=None)]
    assert events == [{"type": "final", "text": "ok"}]
    await client.aclose()


# --- Placement ---------------------------------------------------------------


def test_resolve_engine_name() -> None:
    """Model aliases resolve to engine names; unknowns pass through."""
    assert resolve_engine_name("tts-1") == "kokoro"
    assert resolve_engine_name("whisper-1") == "faster-whisper"
    assert resolve_engine_name("custom") == "custom"


def test_build_registry_local_and_runpod() -> None:
    """The factory honors placement, building local and runpod clients."""
    settings = Settings(
        engine_placement={
            "kokoro": EnginePlacement.LOCAL,
            "chatterbox": EnginePlacement.RUNPOD,
            "faster-whisper": EnginePlacement.LOCAL,
            "pyannote": EnginePlacement.LOCAL,
        }
    )
    reg = build_registry(settings)
    assert isinstance(reg.get("kokoro"), _LC)
    assert isinstance(reg.get("chatterbox"), RunpodEngineClient)
    assert set(reg.names()) == {"kokoro", "chatterbox", "faster-whisper", "pyannote"}
