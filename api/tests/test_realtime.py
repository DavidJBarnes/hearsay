"""Tests for the realtime STT WebSocket handler."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hearsay_api import app_state, db
from hearsay_api.auth import hash_key
from hearsay_api.models import ApiKey
from hearsay_api.queue import JobProcessor
from hearsay_api.routers import realtime
from hearsay_api.storage import LocalDiskBackend


class FakeWebSocket:
    """A scriptable stand-in for a Starlette WebSocket."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self.closed_code: int | None = None
        self._script = list(script)

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    async def receive(self) -> dict[str, Any]:
        if self._script:
            return self._script.pop(0)
        return {"type": "websocket.disconnect"}


@pytest.fixture
def context(registry: Any, tmp_path: Any) -> Any:
    """Install an app context with fake engines for realtime tests."""
    storage = LocalDiskBackend(str(tmp_path / "s"))
    ctx = app_state.AppContext(
        registry=registry,
        storage=storage,
        processor=JobProcessor(registry, storage),
        worker=None,
    )
    app_state.set_context(ctx)
    return ctx


async def test_frame_iterator_stops_on_eof() -> None:
    """The frame iterator yields frames until the EOF sentinel."""
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    await queue.put(b"a")
    await queue.put(b"b")
    await queue.put(realtime._EOF)
    frames = [f async for f in realtime._frame_iterator(queue)]
    assert frames == [b"a", b"b"]


async def test_authenticate(engine_db: None) -> None:
    """Authentication accepts a known key and rejects others."""
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()
    assert await realtime._authenticate("good") is True
    assert await realtime._authenticate("bad") is False
    assert await realtime._authenticate(None) is False


async def test_realtime_happy_path(engine_db: None, context: Any) -> None:
    """A full session emits ready, a partial, and a final transcript."""
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()
    ws = FakeWebSocket(
        [
            {"type": "websocket.receive", "bytes": b"frame-bytes"},
            {"type": "websocket.receive", "text": "not-eof"},  # ignored control text
            {"type": "websocket.receive", "text": "eof"},
        ]
    )
    await realtime.realtime(ws, api_key="good", language="en", model="faster-whisper")
    types = [m["type"] for m in ws.sent]
    assert types[0] == "ready"
    assert "partial" in types
    assert "final" in types


async def test_realtime_unauthorized(engine_db: None, context: Any) -> None:
    """An invalid key yields an error and a 4401 close."""
    ws = FakeWebSocket([])
    await realtime.realtime(ws, api_key="nope", model="faster-whisper")
    assert ws.sent[0]["type"] == "error"
    assert ws.closed_code == 4401


async def test_realtime_unknown_model(engine_db: None, context: Any) -> None:
    """An unknown model yields an error and a 4400 close."""
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()
    ws = FakeWebSocket([])
    await realtime.realtime(ws, api_key="good", model="zzz")
    assert ws.sent[-1]["type"] == "error"
    assert ws.closed_code == 4400


async def test_realtime_disconnect(engine_db: None, context: Any) -> None:
    """A client disconnect ends the loop cleanly."""
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()
    ws = FakeWebSocket([{"type": "websocket.disconnect"}])
    await realtime.realtime(ws, api_key="good", model="faster-whisper")
    assert ws.sent[0]["type"] == "ready"


async def test_realtime_receive_raises_disconnect(engine_db: None, context: Any) -> None:
    """A WebSocketDisconnect raised by receive() is handled gracefully."""
    from fastapi import WebSocketDisconnect

    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()

    class RaisingWebSocket(FakeWebSocket):
        async def receive(self) -> dict[str, Any]:
            raise WebSocketDisconnect(code=1006)

    ws = RaisingWebSocket([])
    await realtime.realtime(ws, api_key="good", model="faster-whisper")
    assert ws.sent[0]["type"] == "ready"


async def test_realtime_emitter_error(engine_db: None, tmp_path: Any) -> None:
    """An error in the emitter is caught and logged, not propagated."""
    from hearsay_api.engines.base import Engine, EngineRegistry

    class ErrorEngine(Engine):
        name = "faster-whisper"
        supports_stt = True

        async def transcribe_stream(self, frames: Any, *, language: str | None = None):
            raise RuntimeError("stream boom")
            yield {}  # pragma: no cover

    reg = EngineRegistry()
    reg.register(ErrorEngine())
    storage = LocalDiskBackend(str(tmp_path / "s2"))
    app_state.set_context(
        app_state.AppContext(
            registry=reg, storage=storage, processor=JobProcessor(reg, storage), worker=None
        )
    )
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("good"), name="t"))
        await session.commit()

    ws = FakeWebSocket([{"type": "websocket.receive", "text": "eof"}])
    await realtime.realtime(ws, api_key="good", model="faster-whisper")
    # ready was sent; emitter error did not crash the handler.
    assert ws.sent[0]["type"] == "ready"
