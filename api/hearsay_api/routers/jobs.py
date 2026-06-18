"""Native batch job endpoints.

Clients enqueue TTS or STT jobs and poll their status/results. Jobs are picked
up asynchronously by the queue worker. STT jobs reference previously stored
audio via ``input_ref``; TTS jobs carry their input text in ``params``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hearsay_api.app_state import get_registry
from hearsay_api.auth import require_api_key
from hearsay_api.db import get_session
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.logging import get_logger
from hearsay_api.models import Job
from hearsay_api.schemas import JobCreate, JobOut

log = get_logger(__name__)
router = APIRouter(prefix="/v1/jobs", dependencies=[Depends(require_api_key)])

_DEFAULT_ENGINE = {"tts": "kokoro", "stt": "faster-whisper"}


@router.get("")
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[JobOut]:
    """Return all jobs, newest first."""
    rows = await session.scalars(select(Job).order_by(Job.created_at.desc()))
    return [JobOut.model_validate(j) for j in rows.all()]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobOut:
    """Return a single job by id."""
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(job)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[EngineRegistry, Depends(get_registry)],
) -> JobOut:
    """Enqueue a new TTS or STT job."""
    engine = body.engine or _DEFAULT_ENGINE[body.type]
    if engine not in registry:
        raise HTTPException(status_code=400, detail=f"unknown engine: {engine}")
    if body.type == "stt" and not body.input_ref:
        raise HTTPException(status_code=400, detail="stt jobs require input_ref")
    if body.type == "tts" and not body.params.get("input"):
        raise HTTPException(status_code=400, detail="tts jobs require params.input")

    job = Job(
        type=body.type,
        engine=engine,
        status="queued",
        params=body.params,
        input_ref=body.input_ref,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    log.info("job enqueued", extra={"extra": {"job_id": job.id, "type": job.type}})
    return JobOut.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete a job and its associated transcript (cascade)."""
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    await session.delete(job)
    await session.commit()
