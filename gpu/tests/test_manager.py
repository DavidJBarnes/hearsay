"""Tests for the GPU model manager."""

from __future__ import annotations

import pytest

from hearsay_gpu.manager import ModelManager


def test_synthesize_concats_and_encodes(manager: ModelManager) -> None:
    """Synthesis concatenates chunks and reports duration."""
    result = manager.synthesize(
        engine="kokoro",
        text="hi",
        voice="af_heart",
        speed=1.0,
        response_format="wav",
        reference_pcm=None,
    )
    assert result["format"] == "wav"
    assert result["sample_rate"] == 24000
    assert result["duration_s"] > 0
    assert result["audio"][:4] == b"RIFF"


def test_synthesize_stream_yields_frames(manager: ModelManager) -> None:
    """Streaming synthesis yields raw PCM frames."""
    frames = list(
        manager.synthesize_stream(
            engine="kokoro", text="hi", voice="v", speed=1.0, reference_pcm=b"ref"
        )
    )
    assert len(frames) == 2
    assert all(isinstance(f, bytes) for f in frames)


def test_transcribe_with_diarization(manager: ModelManager) -> None:
    """Transcription attaches diarization when requested."""
    result = manager.transcribe(
        engine="faster-whisper", pcm16k=b"\x01\x01" * 100, language="en", diarize=True
    )
    assert "heard" in result["text"]
    assert result["diarization"][0]["speaker"] == "SPEAKER_00"


def test_transcribe_without_diarization(manager: ModelManager) -> None:
    """Without diarization the field is None."""
    result = manager.transcribe(
        engine="faster-whisper", pcm16k=b"\x00\x00", language=None, diarize=False
    )
    assert result["diarization"] is None


def test_clone_voice(manager: ModelManager) -> None:
    """Cloning returns metadata including the voice name."""
    meta = manager.clone_voice(
        engine="chatterbox", name="bob", reference_pcm=b"ref-bytes"
    )
    assert meta["name"] == "bob"
    assert meta["reference_bytes"] == len(b"ref-bytes")


def test_clone_voice_unsupported_engine(manager: ModelManager) -> None:
    """Cloning with a non-Chatterbox engine raises."""
    with pytest.raises(KeyError, match="does not support cloning"):
        manager.clone_voice(engine="kokoro", name="x", reference_pcm=b"r")


def test_unknown_engines_raise(manager: ModelManager) -> None:
    """Unknown TTS/STT engine names raise KeyError."""
    with pytest.raises(KeyError, match="unknown tts engine"):
        manager.get_tts("zzz")
    with pytest.raises(KeyError, match="unknown stt engine"):
        manager.get_stt("zzz")


def test_default_manager_constructs_real_wrappers() -> None:
    """A manager with no injected models builds the real wrappers."""
    mgr = ModelManager()
    assert mgr.get_tts("kokoro").name == "kokoro"
    assert mgr.get_tts("chatterbox").name == "chatterbox"
    assert mgr.get_stt("faster-whisper").name == "faster-whisper"
