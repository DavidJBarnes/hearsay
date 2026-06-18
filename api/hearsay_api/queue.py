"""Postgres-backed job queue worker.

Jobs are claimed with ``SELECT ... FOR UPDATE SKIP LOCKED`` so multiple workers
never grab the same row. Work that contends for the same warm GPU model is
serialized with a per-engine lock; non-contending work proceeds concurrently.
No Redis is involved.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hearsay_api.audio import pcm_duration_s, to_pcm16k_mono
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.logging import get_logger
from hearsay_api.metrics import observe_rtf, set_queue_depth
from hearsay_api.models import Job, Transcript, _now
from hearsay_api.storage import StorageBackend

log = get_logger(__name__)


def claim_stmt(dialect_name: str) -> Select[tuple[Job]]:
    """Build the job-claim statement, adding SKIP LOCKED on PostgreSQL."""
    stmt = select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    return stmt


class JobProcessor:
    """Executes a single job against the engine layer and records results."""

    def __init__(self, registry: EngineRegistry, storage: StorageBackend) -> None:
        """Bind the processor to an engine registry and storage backend."""
        self.registry = registry
        self.storage = storage
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _lock_for(self, engine: str) -> asyncio.Lock:
        """Return the serialization lock for a given warm-model engine."""
        return self._locks[engine]

    async def process(self, session: AsyncSession, job: Job) -> None:
        """Run ``job`` to completion, updating its row in ``session``."""
        started = time.perf_counter()
        try:
            async with self._lock_for(job.engine):
                if job.type == "tts":
                    await self._run_tts(job)
                elif job.type == "stt":
                    await self._run_stt(session, job)
                else:
                    raise ValueError(f"unknown job type: {job.type}")
            job.status = "completed"
        except Exception as exc:  # noqa: BLE001 - record any failure on the job
            job.status = "failed"
            job.error = str(exc)
            log.error("job failed", extra={"extra": {"job_id": job.id, "error": str(exc)}})
        finally:
            elapsed = time.perf_counter() - started
            timing = dict(job.timing)
            timing["processing_s"] = elapsed
            job.timing = timing
            job.updated_at = _now()
            await session.commit()

    async def _run_tts(self, job: Job) -> None:
        """Synthesize audio for a TTS job and store the output."""
        engine = self.registry.get(job.engine)
        params = job.params
        reference: bytes | None = None
        ref_ref = params.get("reference_audio_ref")
        if ref_ref:
            reference = await self.storage.get(ref_ref)
        result = await engine.synthesize(
            params["input"],
            voice=params.get("voice", "af_heart"),
            response_format=params.get("response_format", "wav"),
            speed=params.get("speed", 1.0),
            reference_audio=reference,
        )
        out_ref = f"jobs/{job.id}/output.{result.format}"
        await self.storage.put(out_ref, result.audio)
        job.output_ref = out_ref
        timing = dict(job.timing)
        timing["audio_s"] = result.duration_s
        job.timing = timing
        observe_rtf(job.engine, "tts", timing.get("processing_s", 0.0), result.duration_s)

    async def _run_stt(self, session: AsyncSession, job: Job) -> None:
        """Transcribe a STT job's input audio and persist a transcript."""
        engine = self.registry.get(job.engine)
        if not job.input_ref:
            raise ValueError("stt job missing input_ref")
        raw = await self.storage.get(job.input_ref)
        pcm = await to_pcm16k_mono(raw)
        result = await engine.transcribe(
            pcm,
            language=job.params.get("language"),
            diarize=job.params.get("diarize", False),
        )
        transcript = Transcript(
            job_id=job.id,
            text=result.text,
            segments=result.segments,
            language=result.language,
            diarization=result.diarization,
        )
        session.add(transcript)
        audio_s = result.duration or pcm_duration_s(pcm)
        timing = dict(job.timing)
        timing["audio_s"] = audio_s
        job.timing = timing
        observe_rtf(job.engine, "stt", timing.get("processing_s", 0.0), audio_s)


async def refresh_queue_depth(session: AsyncSession) -> dict[str, int]:
    """Recompute and publish per-status job counts; return the counts."""
    rows = await session.execute(select(Job.status, func.count()).group_by(Job.status))
    counts: dict[str, int] = dict(rows.tuples().all())
    set_queue_depth(counts)
    return counts


class QueueWorker:
    """Background loop that claims and processes queued jobs."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        processor: JobProcessor,
        *,
        poll_interval_s: float = 1.0,
    ) -> None:
        """Configure the worker with a session factory and processor."""
        self.sessionmaker = sessionmaker
        self.processor = processor
        self.poll_interval_s = poll_interval_s
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def claim_and_process_once(self) -> bool:
        """Claim and process at most one job; return True if one ran."""
        async with self.sessionmaker() as session:
            assert session.bind is not None
            dialect = session.bind.dialect.name
            job = await session.scalar(claim_stmt(dialect))
            if job is None:
                await refresh_queue_depth(session)
                return False
            job.status = "running"
            job.updated_at = _now()
            await session.commit()
            await self.processor.process(session, job)
            await refresh_queue_depth(session)
            return True

    async def _run(self) -> None:
        """Poll until stopped, sleeping when the queue is empty."""
        log.info("queue worker started")
        while not self._stop.is_set():
            try:
                ran = await self.claim_and_process_once()
            except Exception:  # noqa: BLE001 - worker must never die
                log.error("worker loop error", extra={"extra": {}})
                ran = False
            if not ran:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_s)
        log.info("queue worker stopped")

    def start(self) -> None:
        """Launch the worker loop as a background task."""
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Signal the loop to stop and await its completion."""
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
