"""Tests for the GPU daemon FastAPI app (HTTP + WebSocket)."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from hearsay_gpu import main
from hearsay_gpu.manager import ModelManager


@pytest.fixture
def client(manager: ModelManager) -> TestClient:
    """A TestClient with the fake-model manager installed."""
    main.set_manager(manager)
    app = main.create_app()
    return TestClient(app)


def test_get_manager_uninitialized() -> None:
    """Accessing the manager before init raises."""
    main._manager = None
    with pytest.raises(RuntimeError, match="not initialized"):
        main.get_manager()


def test_health_and_ready(client: TestClient) -> None:
    """Health and readiness endpoints report status."""
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json()["ready"] is True


def test_transcribe_endpoint(client: TestClient) -> None:
    """The transcribe endpoint decodes audio and returns text."""
    audio = base64.b64encode(b"\x01\x01" * 50).decode()
    resp = client.post(
        "/transcribe",
        json={"engine": "faster-whisper", "audio_b64": audio, "diarize": True},
    )
    body = resp.json()
    assert "heard" in body["text"]
    assert body["diarization"][0]["speaker"] == "SPEAKER_00"


def test_synthesize_endpoint(client: TestClient) -> None:
    """The synthesize endpoint returns base64 audio and metadata."""
    resp = client.post(
        "/synthesize",
        json={
            "engine": "kokoro",
            "text": "hi",
            "voice": "af_heart",
            "response_format": "wav",
        },
    )
    body = resp.json()
    assert base64.b64decode(body["audio_b64"])[:4] == b"RIFF"
    assert body["sample_rate"] == 24000


def test_synthesize_with_reference(client: TestClient) -> None:
    """Synthesis accepts a base64 reference sample."""
    ref = base64.b64encode(b"refbytes").decode()
    resp = client.post(
        "/synthesize",
        json={"engine": "chatterbox", "text": "hi", "reference_audio_b64": ref},
    )
    assert resp.status_code == 200


def test_synthesize_stream_endpoint(client: TestClient) -> None:
    """The streaming endpoint returns raw PCM bytes."""
    resp = client.post("/synthesize_stream", json={"engine": "kokoro", "text": "hi"})
    assert resp.status_code == 200
    assert len(resp.content) > 0


def test_synthesize_stream_with_reference(client: TestClient) -> None:
    """Streaming synthesis accepts a reference sample."""
    ref = base64.b64encode(b"r").decode()
    resp = client.post(
        "/synthesize_stream",
        json={"engine": "chatterbox", "text": "hi", "reference_audio_b64": ref},
    )
    assert resp.status_code == 200


def test_clone_endpoint(client: TestClient) -> None:
    """The clone endpoint returns metadata for the reference."""
    ref = base64.b64encode(b"reference").decode()
    resp = client.post(
        "/clone_voice",
        json={"engine": "chatterbox", "name": "bob", "reference_audio_b64": ref},
    )
    assert resp.json()["name"] == "bob"


def test_transcribe_stream_websocket(client: TestClient) -> None:
    """The realtime WS emits a final transcript after speech then EOF."""
    with client.websocket_connect("/transcribe_stream") as ws:
        ws.send_json({"type": "config", "language": "en"})
        ws.send_bytes(b"\x01\x01" * 2048)  # speech
        ws.send_bytes(b"\x00\x00" * 2048)  # silence -> closes utterance
        ws.send_json({"type": "eof"})
        finals = []
        try:
            while True:
                msg = ws.receive_json()
                if msg["type"] == "final":
                    finals.append(msg)
                    if msg.get("eof"):
                        break
        except Exception:  # pragma: no cover - connection closed after final
            pass
    assert any(f.get("eof") for f in finals)
