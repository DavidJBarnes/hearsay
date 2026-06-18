"""Tests for the batch job endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_create_tts_job_and_get(app_client: AsyncClient) -> None:
    """A TTS job is created queued and retrievable."""
    resp = await app_client.post(
        "/v1/jobs",
        json={"type": "tts", "params": {"input": "hello", "voice": "af_heart"}},
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "queued"
    assert job["engine"] == "kokoro"

    fetched = await app_client.get(f"/v1/jobs/{job['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job["id"]


async def test_create_stt_job_requires_input_ref(app_client: AsyncClient) -> None:
    """An STT job without input_ref is rejected."""
    resp = await app_client.post("/v1/jobs", json={"type": "stt"})
    assert resp.status_code == 400


async def test_create_tts_job_requires_input(app_client: AsyncClient) -> None:
    """A TTS job without params.input is rejected."""
    resp = await app_client.post("/v1/jobs", json={"type": "tts", "params": {}})
    assert resp.status_code == 400


async def test_create_job_unknown_engine(app_client: AsyncClient) -> None:
    """A job with an unknown engine is rejected."""
    resp = await app_client.post(
        "/v1/jobs",
        json={"type": "tts", "engine": "zzz", "params": {"input": "hi"}},
    )
    assert resp.status_code == 400


async def test_create_stt_job(app_client: AsyncClient) -> None:
    """An STT job with input_ref is accepted with the default engine."""
    resp = await app_client.post("/v1/jobs", json={"type": "stt", "input_ref": "inputs/x.wav"})
    assert resp.status_code == 201
    assert resp.json()["engine"] == "faster-whisper"


async def test_list_jobs(app_client: AsyncClient) -> None:
    """Jobs are listed newest-first."""
    await app_client.post("/v1/jobs", json={"type": "tts", "params": {"input": "a"}})
    await app_client.post("/v1/jobs", json={"type": "tts", "params": {"input": "b"}})
    resp = await app_client.get("/v1/jobs")
    assert len(resp.json()) >= 2


async def test_get_missing_job(app_client: AsyncClient) -> None:
    """Fetching an unknown job returns 404."""
    resp = await app_client.get("/v1/jobs/nope")
    assert resp.status_code == 404


async def test_delete_job(app_client: AsyncClient) -> None:
    """A job can be deleted; missing jobs 404."""
    created = await app_client.post("/v1/jobs", json={"type": "tts", "params": {"input": "x"}})
    job_id = created.json()["id"]
    resp = await app_client.delete(f"/v1/jobs/{job_id}")
    assert resp.status_code == 204
    assert (await app_client.delete(f"/v1/jobs/{job_id}")).status_code == 404
