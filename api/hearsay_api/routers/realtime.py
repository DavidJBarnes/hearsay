"""Realtime STT over WebSocket.

The browser streams raw PCM frames; we forward them to the streaming STT engine
(VAD-segmented on the GPU daemon) and relay incremental partial and final
transcripts back. Authentication uses a bearer token supplied as the
``api_key`` query parameter (WebSocket clients cannot set arbitrary headers).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from hearsay_api.app_state import get_registry
from hearsay_api.auth import hash_key
from hearsay_api.db import get_sessionmaker
from hearsay_api.logging import get_logger
from hearsay_api.models import ApiKey
from hearsay_api.schemas import RealtimeMessage

log = get_logger(__name__)
router = APIRouter()

_EOF = b""  # sentinel pushed onto the frame queue to signal end of stream


async def _authenticate(api_key: str | None) -> bool:
    """Return whether ``api_key`` matches a stored key hash."""
    if not api_key:
        return False
    async with get_sessionmaker()() as session:
        row = await session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(api_key)))
        return row is not None


async def _frame_iterator(queue: asyncio.Queue[bytes]) -> AsyncIterator[bytes]:
    """Yield PCM frames from ``queue`` until the EOF sentinel is seen."""
    while True:
        frame = await queue.get()
        if frame is _EOF:
            return
        yield frame


@router.websocket("/v1/realtime")
async def realtime(
    websocket: WebSocket,
    api_key: str | None = Query(default=None),
    language: str | None = Query(default=None),
    model: str = Query(default="faster-whisper"),
) -> None:
    """Handle a live realtime STT WebSocket session."""
    await websocket.accept()
    if not await _authenticate(api_key):
        await websocket.send_json(RealtimeMessage(type="error", text="unauthorized").model_dump())
        await websocket.close(code=4401)
        return

    registry = get_registry()
    if model not in registry:
        await websocket.send_json(
            RealtimeMessage(type="error", text=f"unknown model: {model}").model_dump()
        )
        await websocket.close(code=4400)
        return

    engine = registry.get(model)
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await websocket.send_json(RealtimeMessage(type="ready").model_dump())

    async def _emit() -> None:
        """Drive the engine stream and forward events to the client."""
        async for event in engine.transcribe_stream(_frame_iterator(queue), language=language):
            msg = RealtimeMessage(
                type=event.get("type", "partial"),
                text=event.get("text", ""),
                start=event.get("start"),
                end=event.get("end"),
                language=event.get("language"),
            )
            await websocket.send_json(msg.model_dump())

    emitter = asyncio.create_task(_emit())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                await queue.put(data)
            elif message.get("text") == "eof":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await queue.put(_EOF)
        try:
            await emitter
        except Exception as exc:  # noqa: BLE001 - emitter errors must not crash close
            log.warning(
                "realtime emitter ended with error",
                extra={"extra": {"error": repr(exc)}},
            )
