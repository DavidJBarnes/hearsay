"""Tests for the voice management endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_create_preset_and_list(app_client: AsyncClient) -> None:
    """Creating a preset voice (no file) lists it back."""
    resp = await app_client.post("/v1/voices", data={"name": "Narrator", "engine": "kokoro"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "preset"

    listed = await app_client.get("/v1/voices")
    assert any(v["name"] == "Narrator" for v in listed.json())


async def test_create_cloned_voice(app_client: AsyncClient) -> None:
    """Uploading a reference triggers cloning and stores metadata."""
    resp = await app_client.post(
        "/v1/voices",
        data={"name": "MyVoice", "engine": "chatterbox"},
        files={"file": ("ref.wav", b"reference-audio-bytes", "audio/wav")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "cloned"
    assert body["reference_audio_ref"].startswith("voices/")
    assert body["metadata"]["reference_bytes"] == len(b"reference-audio-bytes")


async def test_clone_requires_supported_engine(app_client: AsyncClient) -> None:
    """Cloning with a non-cloning engine is rejected."""
    resp = await app_client.post(
        "/v1/voices",
        data={"name": "X", "engine": "kokoro"},
        files={"file": ("ref.wav", b"data", "audio/wav")},
    )
    assert resp.status_code == 400
    assert "does not support cloning" in resp.json()["detail"]


async def test_clone_empty_reference(app_client: AsyncClient) -> None:
    """An empty reference upload is rejected."""
    resp = await app_client.post(
        "/v1/voices",
        data={"name": "X", "engine": "chatterbox"},
        files={"file": ("ref.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 400


async def test_create_unknown_engine(app_client: AsyncClient) -> None:
    """An unknown engine is rejected with 400."""
    resp = await app_client.post("/v1/voices", data={"name": "X", "engine": "zzz"})
    assert resp.status_code == 400


async def test_delete_voice(app_client: AsyncClient) -> None:
    """Deleting a cloned voice removes it and its reference."""
    created = await app_client.post(
        "/v1/voices",
        data={"name": "Temp", "engine": "chatterbox"},
        files={"file": ("ref.wav", b"abc", "audio/wav")},
    )
    voice_id = created.json()["id"]
    resp = await app_client.delete(f"/v1/voices/{voice_id}")
    assert resp.status_code == 204
    listed = await app_client.get("/v1/voices")
    assert all(v["id"] != voice_id for v in listed.json())


async def test_delete_preset_voice(app_client: AsyncClient) -> None:
    """Deleting a preset voice (no reference audio) succeeds."""
    created = await app_client.post("/v1/voices", data={"name": "PresetTemp", "engine": "kokoro"})
    voice_id = created.json()["id"]
    resp = await app_client.delete(f"/v1/voices/{voice_id}")
    assert resp.status_code == 204


async def test_delete_missing_voice(app_client: AsyncClient) -> None:
    """Deleting an unknown voice returns 404."""
    resp = await app_client.delete("/v1/voices/does-not-exist")
    assert resp.status_code == 404
