"""Shared pytest fixtures: in-memory DB, fake engines, app client.

The engine layer is replaced with in-process fakes so the full HTTP surface can
be exercised without a GPU daemon. A fresh aiosqlite database is created per
test from the ORM metadata.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from hearsay_api import db
from hearsay_api.app_state import AppContext, set_context
from hearsay_api.auth import generate_key, hash_key
from hearsay_api.config import Settings
from hearsay_api.db import Base, set_engine
from hearsay_api.engines.base import Engine, EngineRegistry, SynthesisResult, TranscriptionResult
from hearsay_api.models import ApiKey
from hearsay_api.queue import JobProcessor
from hearsay_api.storage import LocalDiskBackend


class FakeEngine(Engine):
    """In-memory engine producing deterministic outputs for tests."""

    def __init__(
        self,
        name: str,
        *,
        supports_tts: bool = False,
        supports_stt: bool = False,
        supports_cloning: bool = False,
    ) -> None:
        """Configure a fake engine with declared capabilities."""
        self.name = name
        self.supports_tts = supports_tts
        self.supports_stt = supports_stt
        self.supports_cloning = supports_cloning
        self.clone_calls: list[str] = []

    async def transcribe(
        self, audio: bytes, *, language: str | None = None, diarize: bool = False
    ) -> TranscriptionResult:
        """Return a canned transcription echoing the input length."""
        diar = [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}] if diarize else None
        return TranscriptionResult(
            text=f"transcribed {len(audio)} bytes",
            language=language or "en",
            duration=1.0,
            segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
            diarization=diar,
        )

    async def transcribe_stream(
        self, frames: Any, *, language: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield a partial then a final event for each test stream."""
        total = 0
        async for frame in frames:
            total += len(frame)
            yield {"type": "partial", "text": f"partial {total}", "start": 0.0, "end": 0.5}
        yield {"type": "final", "text": "final text", "start": 0.0, "end": 1.0, "eof": True}

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> SynthesisResult:
        """Return canned audio bytes."""
        return SynthesisResult(
            audio=b"RIFFfake" + text.encode("utf-8"),
            format=response_format,
            sample_rate=24000,
            duration_s=1.5,
        )

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str,
        response_format: str = "wav",
        speed: float = 1.0,
        reference_audio: bytes | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield two audio frames."""
        yield b"frame1"
        yield b"frame2"

    async def clone_voice(self, reference_audio: bytes, *, name: str) -> dict[str, Any]:
        """Record the clone call and return metadata."""
        self.clone_calls.append(name)
        return {"engine": self.name, "reference_bytes": len(reference_audio)}


@pytest.fixture(autouse=True)
def _env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point storage at a temp dir and reset the settings cache per test."""
    from hearsay_api.config import get_settings

    monkeypatch.setenv("HEARSAY_STORAGE_LOCAL_ROOT", str(tmp_path / "global_storage"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Any) -> Settings:
    """Return test settings using local disk storage under ``tmp_path``."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        storage_local_root=str(tmp_path / "storage"),
        bootstrap_api_key="sk-test-bootstrap",
        worker_enabled=False,
    )


@pytest.fixture
def registry() -> EngineRegistry:
    """Build a registry of fake engines mirroring the real placement."""
    reg = EngineRegistry()
    reg.register(FakeEngine("kokoro", supports_tts=True))
    reg.register(FakeEngine("chatterbox", supports_tts=True, supports_cloning=True))
    reg.register(FakeEngine("faster-whisper", supports_stt=True))
    reg.register(FakeEngine("pyannote", supports_stt=True))
    return reg


@pytest_asyncio.fixture
async def engine_db() -> AsyncIterator[None]:
    """Create a fresh in-memory database and install it globally."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    set_engine(test_engine)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.reset_engine_state()


@pytest_asyncio.fixture
async def app_client(
    registry: EngineRegistry,
    engine_db: None,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """Yield an authenticated-capable HTTP client against the live app.

    The app lifespan is intercepted to install the fake-engine context instead
    of building real local/RunPod clients and a polling worker.
    """
    storage = LocalDiskBackend(str(tmp_path / "storage"))
    processor = JobProcessor(registry, storage)
    fake_context = AppContext(registry=registry, storage=storage, processor=processor, worker=None)
    monkeypatch.setattr("hearsay_api.main.build_context", lambda _settings: fake_context)

    # Provision the bootstrap key directly so requests can authenticate.
    async with db.get_sessionmaker()() as session:
        session.add(ApiKey(key_hash=hash_key("sk-test-bootstrap"), name="bootstrap"))
        await session.commit()

    from hearsay_api.main import create_app

    app = create_app()
    async with LifespanManager(app, startup_timeout=30, shutdown_timeout=30):
        set_context(fake_context)  # ensure context survives lifespan ordering
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = "Bearer sk-test-bootstrap"
            yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return Authorization headers for the bootstrap key."""
    return {"Authorization": "Bearer sk-test-bootstrap"}


__all__ = ["FakeEngine", "generate_key"]
