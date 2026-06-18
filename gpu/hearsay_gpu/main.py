"""GPU daemon FastAPI app: warm-model RPC over HTTP + WebSocket.

Thin transport layer over :class:`~hearsay_gpu.manager.ModelManager`. Endpoints
mirror the :class:`LocalEngineClient` contract used by the API gateway.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from hearsay_gpu.config import get_gpu_settings
from hearsay_gpu.logging import configure_logging, get_logger
from hearsay_gpu.manager import ModelManager
from hearsay_gpu.realtime import RealtimeSession

log = get_logger(__name__)

_manager: ModelManager | None = None


def set_manager(manager: ModelManager) -> None:
    """Install the active model manager (used by startup and tests)."""
    global _manager
    _manager = manager


def get_manager() -> ModelManager:
    """Return the active model manager or raise if uninitialized."""
    if _manager is None:
        raise RuntimeError("model manager not initialized")
    return _manager


class TranscribeRequest(BaseModel):
    """Payload for ``POST /transcribe``."""

    engine: str = "faster-whisper"
    audio_b64: str
    language: str | None = None
    diarize: bool = False


class SynthesizeRequest(BaseModel):
    """Payload for ``POST /synthesize`` and ``/synthesize_stream``."""

    engine: str = "kokoro"
    text: str
    voice: str = "af_heart"
    response_format: str = "wav"
    speed: float = 1.0
    reference_audio_b64: str | None = None


class CloneRequest(BaseModel):
    """Payload for ``POST /clone_voice``."""

    engine: str = "chatterbox"
    name: str
    reference_audio_b64: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging, build the manager, and preload warm models."""
    settings = get_gpu_settings()
    configure_logging(settings.log_level)
    if _manager is None:
        manager = ModelManager(settings)
        manager.preload()
        set_manager(manager)
    log.info("gpu daemon started")
    yield
    log.info("gpu daemon stopped")


def create_app() -> FastAPI:
    """Create and configure the GPU daemon application."""
    app = FastAPI(title="Hearsay GPU", version="1.0.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, bool]:
        """Readiness probe: the manager must be initialized."""
        return {"ready": _manager is not None}

    @app.post("/transcribe")
    async def transcribe(
        body: TranscribeRequest, manager: Annotated[ModelManager, Depends(get_manager)]
    ) -> dict[str, Any]:
        """Transcribe a base64 PCM buffer."""
        pcm = base64.b64decode(body.audio_b64)
        return manager.transcribe(
            engine=body.engine, pcm16k=pcm, language=body.language, diarize=body.diarize
        )

    @app.post("/synthesize")
    async def synthesize(
        body: SynthesizeRequest, manager: Annotated[ModelManager, Depends(get_manager)]
    ) -> dict[str, Any]:
        """Synthesize and return base64-encoded audio."""
        reference = (
            base64.b64decode(body.reference_audio_b64)
            if body.reference_audio_b64
            else None
        )
        result = manager.synthesize(
            engine=body.engine,
            text=body.text,
            voice=body.voice,
            speed=body.speed,
            response_format=body.response_format,
            reference_pcm=reference,
        )
        return {
            "audio_b64": base64.b64encode(result["audio"]).decode("ascii"),
            "format": result["format"],
            "sample_rate": result["sample_rate"],
            "duration_s": result["duration_s"],
        }

    @app.post("/synthesize_stream")
    async def synthesize_stream(
        body: SynthesizeRequest, manager: Annotated[ModelManager, Depends(get_manager)]
    ) -> StreamingResponse:
        """Stream raw int16 PCM frames as they are synthesized."""
        reference = (
            base64.b64decode(body.reference_audio_b64)
            if body.reference_audio_b64
            else None
        )

        async def _frames() -> AsyncIterator[bytes]:
            for frame in manager.synthesize_stream(
                engine=body.engine,
                text=body.text,
                voice=body.voice,
                speed=body.speed,
                reference_pcm=reference,
            ):
                yield frame

        return StreamingResponse(_frames(), media_type="audio/L16")

    @app.post("/clone_voice")
    async def clone_voice(
        body: CloneRequest, manager: Annotated[ModelManager, Depends(get_manager)]
    ) -> dict[str, Any]:
        """Produce cloning metadata for a reference sample."""
        reference = base64.b64decode(body.reference_audio_b64)
        return manager.clone_voice(
            engine=body.engine, name=body.name, reference_pcm=reference
        )

    @app.websocket("/transcribe_stream")
    async def transcribe_stream(websocket: WebSocket) -> None:
        """Realtime STT: receive PCM frames, emit partial/final transcripts."""
        await websocket.accept()
        manager = get_manager()
        await _run_realtime(websocket, manager)

    return app


async def _run_realtime(websocket: WebSocket, manager: ModelManager) -> None:
    """Drive a realtime STT WebSocket session against ``manager``."""
    settings = manager.settings
    language: str | None = None

    def _transcribe(pcm: bytes) -> str:
        return manager.get_stt("faster-whisper").transcribe(pcm, language=language).text

    def _speech_prob(window: bytes) -> float:
        return manager.vad.speech_prob(window, settings.sample_rate)

    session = RealtimeSession(
        transcribe=_transcribe,
        speech_prob=_speech_prob,
        sample_rate=settings.sample_rate,
    )

    async def _send(
        event_type: str, text: str, start: float, end: float, eof: bool
    ) -> None:
        await websocket.send_text(
            json.dumps(
                {
                    "type": event_type,
                    "text": text,
                    "start": start,
                    "end": end,
                    "eof": eof,
                }
            )
        )

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                for ev in session.feed(data):
                    await _send(ev.type, ev.text, ev.start, ev.end, False)
            elif (text := message.get("text")) is not None:
                payload = json.loads(text)
                if payload.get("type") == "config":
                    language = payload.get("language")
                elif payload.get("type") == "eof":
                    break
    except WebSocketDisconnect:  # pragma: no cover - network-dependent
        return
    for ev in session.flush():
        await _send(ev.type, ev.text, ev.start, ev.end, True)


app = create_app()
