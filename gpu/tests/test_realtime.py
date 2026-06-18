"""Tests for the VAD-segmented realtime session."""

from __future__ import annotations

from hearsay_gpu.realtime import RealtimeSession


def _session(**kwargs: object) -> RealtimeSession:
    """Build a session with simple speech/transcribe stubs."""
    transcripts = {"calls": 0}

    def transcribe(pcm: bytes) -> str:
        transcripts["calls"] += 1
        return f"text-{len(pcm)}"

    def speech_prob(window: bytes) -> float:
        return 1.0 if any(window) else 0.0

    return RealtimeSession(
        transcribe=transcribe,
        speech_prob=speech_prob,
        sample_rate=16000,
        window_bytes=4,
        threshold=0.5,
        min_silence_windows=2,
        partial_every_windows=2,
        **kwargs,  # type: ignore[arg-type]
    )


def test_partial_then_final() -> None:
    """Speech emits partials, then silence closes the utterance with a final."""
    session = _session()
    events: list[tuple[str, str]] = []
    # 4 speech windows (non-zero) -> at least one partial at window 2 and 4.
    for _ in range(4):
        for ev in session.feed(b"\x01\x01\x01\x01"):
            events.append((ev.type, ev.text))
    # 2 silence windows -> final.
    for _ in range(2):
        for ev in session.feed(b"\x00\x00\x00\x00"):
            events.append((ev.type, ev.text))
    types = [t for t, _ in events]
    assert "partial" in types
    assert types[-1] == "final"


def test_flush_finalizes_pending() -> None:
    """Flush finalizes an in-progress utterance and folds a trailing window."""
    session = _session()
    list(session.feed(b"\x01\x01\x01\x01"))  # one speech window, no final yet
    # Feed a partial (sub-window) chunk so _pending is non-empty at flush.
    list(session.feed(b"\x01\x01"))
    events = list(session.flush())
    assert events
    assert events[-1].type == "final"


def test_flush_without_speech_is_noop() -> None:
    """Flushing with no speech produces no events."""
    session = _session()
    list(session.feed(b"\x00\x00\x00\x00"))
    assert list(session.flush()) == []
