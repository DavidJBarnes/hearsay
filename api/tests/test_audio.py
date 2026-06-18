"""Tests for audio helpers (with injected ffmpeg runners and the real binary)."""

from __future__ import annotations

import pytest

from hearsay_api import audio


async def _ok_runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
    """A fake ffmpeg runner that echoes its stdin."""
    return 0, b"PCM:" + stdin, b""


async def _fail_runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
    """A fake ffmpeg runner that reports failure."""
    return 1, b"", b"bad input"


async def test_to_pcm16k_mono_uses_runner() -> None:
    """The normalizer returns the runner's stdout on success."""
    out = await audio.to_pcm16k_mono(b"in", runner=_ok_runner)
    assert out == b"PCM:in"


async def test_to_pcm16k_mono_raises_on_failure() -> None:
    """A non-zero return code raises with stderr in the message."""
    with pytest.raises(RuntimeError, match="bad input"):
        await audio.to_pcm16k_mono(b"in", runner=_fail_runner)


async def test_transcode_each_format() -> None:
    """Transcoding maps each format and returns runner output."""
    for fmt in ("wav", "mp3", "opus", "flac", "pcm"):
        out = await audio.transcode(b"x", out_format=fmt, runner=_ok_runner)
        assert out == b"PCM:x"


async def test_transcode_failure() -> None:
    """Transcode failure raises a RuntimeError."""
    with pytest.raises(RuntimeError):
        await audio.transcode(b"x", out_format="wav", runner=_fail_runner)


def test_pcm_duration() -> None:
    """PCM duration is frames / sample_rate."""
    assert audio.pcm_duration_s(b"\x00\x00" * 16000, sample_rate=16000) == 1.0
    assert audio.pcm_duration_s(b"", sample_rate=16000) == 0.0
    assert audio.pcm_duration_s(b"\x00\x00", sample_rate=0) == 0.0


async def test_default_runner_with_real_ffmpeg() -> None:
    """The default runner invokes the real ffmpeg binary end to end."""
    # 0.1s of silence at 16k mono s16le wrapped in WAV via ffmpeg.
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    pcm = await audio.to_pcm16k_mono(buf.getvalue())
    assert len(pcm) > 0
