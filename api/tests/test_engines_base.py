"""Tests for the engine interface, registry, and RunPod stub."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from hearsay_api.engines.base import Engine, EngineRegistry


class BareEngine(Engine):
    """An engine that overrides nothing (exercises default raises)."""

    name = "bare"


async def _empty() -> AsyncIterator[bytes]:
    """An empty async frame iterator."""
    return
    yield b""  # pragma: no cover


async def test_default_methods_raise() -> None:
    """All capability methods raise NotImplementedError by default."""
    e = BareEngine()
    with pytest.raises(NotImplementedError):
        await e.transcribe(b"x")
    with pytest.raises(NotImplementedError):
        await e.synthesize("hi", voice="v")
    with pytest.raises(NotImplementedError):
        await e.clone_voice(b"x", name="n")
    with pytest.raises(NotImplementedError):
        async for _ in e.transcribe_stream(_empty()):
            pass
    with pytest.raises(NotImplementedError):
        async for _ in e.synthesize_stream("hi", voice="v"):
            pass


def test_registry_register_get_contains() -> None:
    """Registry register/get/contains/names behave as expected."""
    reg = EngineRegistry()
    e = BareEngine()
    reg.register(e)
    assert reg.get("bare") is e
    assert "bare" in reg
    assert reg.names() == ["bare"]


def test_registry_unknown_raises() -> None:
    """Looking up an unknown engine lists the available ones."""
    reg = EngineRegistry()
    with pytest.raises(KeyError, match="registered engines"):
        reg.get("nope")


async def test_runpod_stub_raises_everything() -> None:
    """The RunPod stub raises NotImplementedError on every capability."""
    from hearsay_api.engines.runpod_client import RunpodEngineClient

    e = RunpodEngineClient(
        "chatterbox", endpoint=None, api_key=None, supports_tts=True, supports_cloning=True
    )
    with pytest.raises(NotImplementedError, match="not implemented in v1"):
        await e.transcribe(b"x")
    with pytest.raises(NotImplementedError):
        await e.synthesize("hi", voice="v")
    with pytest.raises(NotImplementedError):
        await e.clone_voice(b"x", name="n")
    with pytest.raises(NotImplementedError):
        async for _ in e.transcribe_stream(_empty()):
            pass
    with pytest.raises(NotImplementedError):
        async for _ in e.synthesize_stream("hi", voice="v"):
            pass
