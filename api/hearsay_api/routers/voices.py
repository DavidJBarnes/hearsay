"""Native voice management endpoints.

List, create, and delete voices. Creating a voice with a reference audio sample
triggers Chatterbox voice cloning; the reference is stored and the cloning
metadata persisted with the voice.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hearsay_api.app_state import get_registry, get_storage
from hearsay_api.auth import require_api_key
from hearsay_api.db import get_session
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.logging import get_logger
from hearsay_api.models import Voice
from hearsay_api.schemas import VoiceOut
from hearsay_api.storage import StorageBackend

log = get_logger(__name__)
router = APIRouter(prefix="/v1/voices", dependencies=[Depends(require_api_key)])


@router.get("")
async def list_voices(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[VoiceOut]:
    """Return all voices ordered by creation time."""
    rows = await session.scalars(select(Voice).order_by(Voice.created_at))
    return [VoiceOut.model_validate(v) for v in rows.all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_voice(
    session: Annotated[AsyncSession, Depends(get_session)],
    registry: Annotated[EngineRegistry, Depends(get_registry)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    name: Annotated[str, Form()],
    engine: Annotated[str, Form()] = "chatterbox",
    file: Annotated[UploadFile | None, File()] = None,
) -> VoiceOut:
    """Create a preset voice, or a cloned voice when a reference is uploaded."""
    if engine not in registry:
        raise HTTPException(status_code=400, detail=f"unknown engine: {engine}")

    if file is None:
        voice = Voice(name=name, engine=engine, type="preset", voice_metadata={})
        session.add(voice)
        await session.commit()
        await session.refresh(voice)
        return VoiceOut.model_validate(voice)

    engine_impl = registry.get(engine)
    if not engine_impl.supports_cloning:
        raise HTTPException(status_code=400, detail=f"engine '{engine}' does not support cloning")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty reference audio")

    voice = Voice(name=name, engine=engine, type="cloned", voice_metadata={})
    session.add(voice)
    await session.flush()  # assign id for the ref path

    ref = f"voices/{voice.id}/reference"
    await storage.put(ref, raw)
    clone_meta = await engine_impl.clone_voice(raw, name=name)
    voice.reference_audio_ref = ref
    voice.voice_metadata = clone_meta
    await session.commit()
    await session.refresh(voice)
    log.info("created cloned voice", extra={"extra": {"voice_id": voice.id}})
    return VoiceOut.model_validate(voice)


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice(
    voice_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> None:
    """Delete a voice and any stored reference audio."""
    voice = await session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="voice not found")
    if voice.reference_audio_ref:
        await storage.delete(voice.reference_audio_ref)
    await session.delete(voice)
    await session.commit()
