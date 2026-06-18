"""Tests for the job queue worker and processor."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hearsay_api import db
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.models import Job, Transcript
from hearsay_api.queue import JobProcessor, QueueWorker, claim_stmt, refresh_queue_depth
from hearsay_api.storage import LocalDiskBackend


def test_claim_stmt_dialects() -> None:
    """SKIP LOCKED is added only for PostgreSQL."""
    pg = claim_stmt("postgresql")
    sqlite = claim_stmt("sqlite")
    assert pg._for_update_arg is not None
    assert sqlite._for_update_arg is None


@pytest.fixture
def processor(registry: EngineRegistry, tmp_path: Any) -> JobProcessor:
    """A processor backed by fake engines and disk storage."""
    return JobProcessor(registry, LocalDiskBackend(str(tmp_path / "s")))


async def _add_job(**kwargs: Any) -> Job:
    """Insert a job row and return it."""
    job = Job(**kwargs)
    async with db.get_sessionmaker()() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    return job


async def test_process_tts(engine_db: None, processor: JobProcessor) -> None:
    """A TTS job synthesizes audio and stores the output ref."""
    job = await _add_job(type="tts", engine="kokoro", status="running", params={"input": "hi"})
    async with db.get_sessionmaker()() as session:
        merged = await session.get(Job, job.id)
        await processor.process(session, merged)
    async with db.get_sessionmaker()() as session:
        done = await session.get(Job, job.id)
    assert done.status == "completed"
    assert done.output_ref.endswith("output.wav")
    assert done.timing["audio_s"] == 1.5
    assert await processor.storage.exists(done.output_ref)


async def test_process_tts_with_reference(engine_db: None, processor: JobProcessor) -> None:
    """A TTS job with a stored reference loads it before synthesis."""
    await processor.storage.put("refs/r.wav", b"ref-bytes")
    job = await _add_job(
        type="tts",
        engine="chatterbox",
        status="running",
        params={"input": "hi", "reference_audio_ref": "refs/r.wav"},
    )
    async with db.get_sessionmaker()() as session:
        merged = await session.get(Job, job.id)
        await processor.process(session, merged)
    async with db.get_sessionmaker()() as session:
        done = await session.get(Job, job.id)
    assert done.status == "completed"


async def test_process_stt(
    engine_db: None, processor: JobProcessor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An STT job transcribes input audio and writes a transcript."""

    async def fake_pcm(data: bytes, **kwargs: Any) -> bytes:
        return b"\x00\x00" * 16000

    monkeypatch.setattr("hearsay_api.queue.to_pcm16k_mono", fake_pcm)
    await processor.storage.put("inputs/a.wav", b"raw-audio")
    job = await _add_job(
        type="stt", engine="faster-whisper", status="running", input_ref="inputs/a.wav"
    )
    async with db.get_sessionmaker()() as session:
        merged = await session.get(Job, job.id)
        await processor.process(session, merged)
    from sqlalchemy import select

    async with db.get_sessionmaker()() as session:
        done = await session.get(Job, job.id)
        t = (await session.scalars(select(Transcript))).first()
    assert done.status == "completed"
    assert t is not None
    assert "transcribed" in t.text


async def test_process_stt_missing_input(engine_db: None, processor: JobProcessor) -> None:
    """An STT job with no input_ref fails with an error."""
    job = await _add_job(type="stt", engine="faster-whisper", status="running", input_ref=None)
    async with db.get_sessionmaker()() as session:
        merged = await session.get(Job, job.id)
        await processor.process(session, merged)
    async with db.get_sessionmaker()() as session:
        done = await session.get(Job, job.id)
    assert done.status == "failed"
    assert "input_ref" in done.error


async def test_process_unknown_type(engine_db: None, processor: JobProcessor) -> None:
    """An unknown job type is recorded as a failure."""
    job = await _add_job(type="weird", engine="kokoro", status="running", params={})
    async with db.get_sessionmaker()() as session:
        merged = await session.get(Job, job.id)
        await processor.process(session, merged)
    async with db.get_sessionmaker()() as session:
        done = await session.get(Job, job.id)
    assert done.status == "failed"
    assert "unknown job type" in done.error


async def test_refresh_queue_depth(engine_db: None) -> None:
    """Queue-depth counts are computed per status."""
    await _add_job(type="tts", engine="kokoro", status="queued", params={"input": "x"})
    await _add_job(type="tts", engine="kokoro", status="completed", params={"input": "y"})
    async with db.get_sessionmaker()() as session:
        counts = await refresh_queue_depth(session)
    assert counts["queued"] == 1
    assert counts["completed"] == 1


async def test_worker_claims_and_processes(engine_db: None, processor: JobProcessor) -> None:
    """The worker claims a queued job, runs it, and marks it completed."""
    await _add_job(type="tts", engine="kokoro", status="queued", params={"input": "hi"})
    worker = QueueWorker(db.get_sessionmaker(), processor, poll_interval_s=0.01)
    assert await worker.claim_and_process_once() is True
    assert await worker.claim_and_process_once() is False  # empty now
    from sqlalchemy import select

    async with db.get_sessionmaker()() as session:
        job = (await session.scalars(select(Job))).first()
    assert job.status == "completed"


async def test_worker_run_loop(engine_db: None, processor: JobProcessor) -> None:
    """The background loop processes a job then idles until stopped."""
    await _add_job(type="tts", engine="kokoro", status="queued", params={"input": "hi"})
    worker = QueueWorker(db.get_sessionmaker(), processor, poll_interval_s=0.01)
    worker.start()
    await asyncio.sleep(0.1)  # let it process + idle-poll (TimeoutError branch)
    await worker.stop()
    await worker.stop()  # idempotent when already stopped


async def test_worker_loop_handles_exception(
    engine_db: None, processor: JobProcessor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception in the loop is caught and does not kill the worker."""
    worker = QueueWorker(db.get_sessionmaker(), processor, poll_interval_s=0.01)

    async def boom() -> bool:
        worker._stop.set()
        raise RuntimeError("kaboom")

    monkeypatch.setattr(worker, "claim_and_process_once", boom)
    worker.start()
    await asyncio.sleep(0.05)  # let the loop run boom (which sets stop) at least once
    await worker.stop()
