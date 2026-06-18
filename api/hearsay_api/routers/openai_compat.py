"""OpenAI-compatible audio endpoints.

``POST /v1/audio/speech`` and ``POST /v1/audio/transcriptions`` mirror the
OpenAI shapes so existing clients work unchanged, while routing through the
Hearsay engine abstraction.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from hearsay_api.app_state import get_registry
from hearsay_api.audio import pcm_duration_s, to_pcm16k_mono
from hearsay_api.auth import require_api_key
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.engines.placement import resolve_engine_name
from hearsay_api.logging import get_logger
from hearsay_api.metrics import observe_rtf, observe_ttfa
from hearsay_api.schemas import SpeechRequest, TranscriptionResponse, TranscriptionSegment

log = get_logger(__name__)
router = APIRouter(prefix="/v1/audio", dependencies=[Depends(require_api_key)])

CONTENT_TYPES: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "flac": "audio/flac",
    "pcm": "audio/L16",
}


def _engine_for(model: str, registry: EngineRegistry) -> str:
    """Resolve and validate the engine name for a request ``model``."""
    name = resolve_engine_name(model)
    if name not in registry:
        raise HTTPException(status_code=400, detail=f"unknown model/engine: {model}")
    return name


@router.post("/speech")
async def create_speech(
    body: SpeechRequest,
    registry: Annotated[EngineRegistry, Depends(get_registry)],
) -> Response:
    """Synthesize speech, optionally streaming chunked audio frames."""
    engine_name = _engine_for(body.model, registry)
    engine = registry.get(engine_name)
    media_type = CONTENT_TYPES[body.response_format]

    if body.stream:
        start = time.perf_counter()

        async def _frames() -> AsyncIterator[bytes]:
            first = True
            async for chunk in engine.synthesize_stream(
                body.input,
                voice=body.voice,
                response_format=body.response_format,
                speed=body.speed,
            ):
                if first:
                    observe_ttfa(engine_name, "tts", time.perf_counter() - start)
                    first = False
                yield chunk

        return StreamingResponse(_frames(), media_type=media_type)

    start = time.perf_counter()
    result = await engine.synthesize(
        body.input,
        voice=body.voice,
        response_format=body.response_format,
        speed=body.speed,
    )
    observe_ttfa(engine_name, "tts", time.perf_counter() - start)
    observe_rtf(engine_name, "tts", time.perf_counter() - start, result.duration_s)
    return Response(content=result.audio, media_type=media_type)


@router.post("/transcriptions", response_model=None)
async def create_transcription(
    registry: Annotated[EngineRegistry, Depends(get_registry)],
    file: Annotated[UploadFile, File()],
    model: Annotated[str, Form()] = "whisper-1",
    language: Annotated[str | None, Form()] = None,
    response_format: Annotated[str, Form()] = "json",
    diarize: Annotated[bool, Form()] = False,
) -> Response | TranscriptionResponse | dict[str, str]:
    """Transcribe an uploaded audio file (OpenAI ``transcriptions`` shape)."""
    engine_name = _engine_for(model, registry)
    engine = registry.get(engine_name)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio file")
    pcm = await to_pcm16k_mono(raw)

    start = time.perf_counter()
    result = await engine.transcribe(pcm, language=language, diarize=diarize)
    elapsed = time.perf_counter() - start
    audio_s = result.duration or pcm_duration_s(pcm)
    observe_rtf(engine_name, "stt", elapsed, audio_s)

    if response_format == "text":
        return Response(content=result.text, media_type="text/plain")
    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        duration=audio_s,
        segments=[TranscriptionSegment(**s) for s in result.segments],
        diarization=result.diarization,
    )
