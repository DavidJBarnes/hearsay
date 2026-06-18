"""Tests for the GPU daemon audio helpers."""

from __future__ import annotations

import wave

import pytest

from hearsay_gpu import audio


def test_floats_to_pcm16_clamps() -> None:
    """Float samples are clamped to [-1, 1] and packed as int16."""
    pcm = audio.floats_to_pcm16([0.0, 1.5, -1.5])
    assert len(pcm) == 6  # 3 samples * 2 bytes
    # 1.5 clamps to 1.0 -> 32767; -1.5 clamps to -1.0 -> -32767.
    import array

    arr = array.array("h")
    arr.frombytes(pcm)
    assert arr[1] == 32767
    assert arr[2] == -32767


def test_pcm16_to_wav_roundtrip() -> None:
    """WAV wrapping yields a readable container with the right params."""
    import io

    pcm = audio.floats_to_pcm16([0.0] * 1600)
    wav_bytes = audio.pcm16_to_wav(pcm, sample_rate=16000)
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2


def test_encode_pcm_and_wav() -> None:
    """PCM passthrough and WAV encoding need no ffmpeg."""
    pcm = b"\x00\x00" * 10
    assert audio.encode(pcm, sample_rate=16000, out_format="pcm") == pcm
    assert audio.encode(pcm, sample_rate=16000, out_format="wav")[:4] == b"RIFF"


def test_encode_compressed_uses_runner() -> None:
    """Compressed formats invoke the (injected) ffmpeg runner."""

    def runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
        assert "mp3" in argv
        return 0, b"MP3DATA", b""

    out = audio.encode(b"\x00\x00", sample_rate=16000, out_format="mp3", runner=runner)
    assert out == b"MP3DATA"


def test_encode_failure_raises() -> None:
    """A non-zero ffmpeg return code raises."""

    def runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
        return 1, b"", b"boom"

    with pytest.raises(RuntimeError, match="boom"):
        audio.encode(b"x", sample_rate=16000, out_format="opus", runner=runner)


def test_encode_real_ffmpeg_flac() -> None:
    """The default runner encodes FLAC with the real ffmpeg binary."""
    pcm = audio.floats_to_pcm16([0.0] * 1600)
    out = audio.encode(pcm, sample_rate=16000, out_format="flac")
    assert out[:4] == b"fLaC"
