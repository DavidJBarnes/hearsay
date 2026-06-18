"""VAD-segmented rolling-buffer realtime STT.

A :class:`RealtimeSession` consumes PCM frames, tracks speech/silence using a
VAD probability callback, and emits incremental *partial* transcripts as audio
accumulates and a *final* transcript when an utterance closes (a run of silence
after speech). The transcription and VAD functions are injected so the logic is
fully unit-testable without GPU models.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass(slots=True)
class RealtimeEvent:
    """An event emitted by the realtime session."""

    type: str  # "partial" | "final"
    text: str
    start: float
    end: float


class RealtimeSession:
    """Rolling-buffer segmenter emitting partial and final transcripts."""

    def __init__(
        self,
        *,
        transcribe: Callable[[bytes], str],
        speech_prob: Callable[[bytes], float],
        sample_rate: int = 16000,
        window_bytes: int = 1024,
        threshold: float = 0.5,
        min_silence_windows: int = 15,
        partial_every_windows: int = 8,
    ) -> None:
        """Configure the session with injected transcribe/VAD callables."""
        self.transcribe = transcribe
        self.speech_prob = speech_prob
        self.sample_rate = sample_rate
        self.window_bytes = window_bytes
        self.threshold = threshold
        self.min_silence_windows = min_silence_windows
        self.partial_every_windows = partial_every_windows

        self._pending = bytearray()  # frames not yet aligned to a window
        self._utterance = bytearray()  # current utterance audio
        self._silence_run = 0
        self._has_speech = False
        self._windows_since_partial = 0
        self._utterance_start_s = 0.0
        self._elapsed_bytes = 0

    def _now_s(self) -> float:
        """Return elapsed audio time in seconds."""
        return self._elapsed_bytes / (self.sample_rate * 2)

    def feed(self, frame: bytes) -> Iterator[RealtimeEvent]:
        """Feed a PCM ``frame`` and yield any resulting events."""
        self._pending.extend(frame)
        while len(self._pending) >= self.window_bytes:
            window = bytes(self._pending[: self.window_bytes])
            del self._pending[: self.window_bytes]
            yield from self._process_window(window)

    def _process_window(self, window: bytes) -> Iterator[RealtimeEvent]:
        """Update state for one aligned window and emit events."""
        self._elapsed_bytes += len(window)
        is_speech = self.speech_prob(window) >= self.threshold

        if is_speech:
            if not self._has_speech:
                self._utterance_start_s = self._now_s()
            self._has_speech = True
            self._silence_run = 0
            self._utterance.extend(window)
            self._windows_since_partial += 1
            if self._windows_since_partial >= self.partial_every_windows:
                self._windows_since_partial = 0
                text = self.transcribe(bytes(self._utterance))
                yield RealtimeEvent(
                    "partial", text, self._utterance_start_s, self._now_s()
                )
        elif self._has_speech:
            self._utterance.extend(window)
            self._silence_run += 1
            if self._silence_run >= self.min_silence_windows:
                yield from self._finalize()

    def _finalize(self) -> Iterator[RealtimeEvent]:
        """Emit a final event for the current utterance and reset state."""
        if self._utterance:
            text = self.transcribe(bytes(self._utterance))
            yield RealtimeEvent("final", text, self._utterance_start_s, self._now_s())
        self._utterance = bytearray()
        self._has_speech = False
        self._silence_run = 0
        self._windows_since_partial = 0

    def flush(self) -> Iterator[RealtimeEvent]:
        """Finalize any in-progress utterance at end of stream."""
        if self._pending:
            # Fold the trailing partial window into the utterance if mid-speech.
            if self._has_speech:
                self._utterance.extend(self._pending)
            self._elapsed_bytes += len(self._pending)
            self._pending = bytearray()
        if self._has_speech:
            yield from self._finalize()
