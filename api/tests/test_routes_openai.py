"""Tests for the OpenAI-compatible speech/transcription endpoints."""

from __future__ import annotations

import io
import wave

from httpx import AsyncClient

from hearsay_api.engines.base import EngineError, EngineRegistry
from tests.conftest import FakeEngine


def _wav_bytes(seconds: float = 0.1) -> bytes:
    """Return a small valid WAV buffer of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


async def test_speech_non_streaming(app_client: AsyncClient) -> None:
    """A basic speech request returns audio bytes with the right type."""
    resp = await app_client.post(
        "/v1/audio/speech",
        json={"model": "kokoro", "input": "hello", "voice": "af_heart"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content.startswith(b"RIFFfake")


async def test_speech_streaming(app_client: AsyncClient) -> None:
    """A streaming speech request returns concatenated frames."""
    resp = await app_client.post(
        "/v1/audio/speech",
        json={"model": "tts-1", "input": "hi", "stream": True, "response_format": "mp3"},
    )
    assert resp.status_code == 200
    assert resp.content == b"frame1frame2"


async def test_speech_engine_error_surfaces_detail(
    app_client: AsyncClient, registry: EngineRegistry
) -> None:
    """An engine failure returns its upstream status and real cause, not a 500."""

    class BoomEngine(FakeEngine):
        async def synthesize(self, *args: object, **kwargs: object) -> object:
            raise EngineError(502, "engine 'kokoro': RuntimeError: chatterbox exploded")

    registry.register(BoomEngine("kokoro", supports_tts=True))
    resp = await app_client.post("/v1/audio/speech", json={"model": "kokoro", "input": "hi"})
    assert resp.status_code == 502
    assert "chatterbox exploded" in resp.json()["detail"]


async def test_speech_unknown_model(app_client: AsyncClient) -> None:
    """An unknown model is rejected with 400."""
    resp = await app_client.post("/v1/audio/speech", json={"model": "nope", "input": "hi"})
    assert resp.status_code == 400


async def test_speech_requires_auth(app_client: AsyncClient) -> None:
    """Missing credentials are rejected with 401."""
    resp = await app_client.post(
        "/v1/audio/speech",
        json={"model": "kokoro", "input": "hi"},
        headers={"Authorization": ""},
    )
    assert resp.status_code == 401


async def test_transcription_json(app_client: AsyncClient) -> None:
    """A transcription returns verbose JSON with segments."""
    resp = await app_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"model": "whisper-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "transcribed" in body["text"]
    assert body["segments"][0]["text"] == "hello"


async def test_transcription_text_format(app_client: AsyncClient) -> None:
    """``response_format=text`` returns plain text."""
    resp = await app_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"model": "whisper-1", "response_format": "text"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "transcribed" in resp.text


async def test_transcription_with_diarization(app_client: AsyncClient) -> None:
    """Requesting diarization includes turns in the response."""
    resp = await app_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"model": "whisper-1", "diarize": "true"},
    )
    assert resp.json()["diarization"][0]["speaker"] == "SPEAKER_00"


async def test_transcription_empty_file(app_client: AsyncClient) -> None:
    """An empty upload is rejected with 400."""
    resp = await app_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", b"", "audio/wav")},
        data={"model": "whisper-1"},
    )
    assert resp.status_code == 400


async def test_transcription_unknown_model(app_client: AsyncClient) -> None:
    """An unknown STT model is rejected with 400."""
    resp = await app_client.post(
        "/v1/audio/transcriptions",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"model": "nope"},
    )
    assert resp.status_code == 400
