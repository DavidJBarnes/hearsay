"""Silero VAD wrapper for realtime segmentation.

Exposes a per-window speech-probability function. Heavy imports (``torch``,
``silero-vad``) happen only in :meth:`_do_load`. The realtime segmenter uses the
probabilities to decide when an utterance has ended.
"""

from __future__ import annotations

from typing import Any

from hearsay_gpu.logging import get_logger
from hearsay_gpu.models.base import ModelWrapper

log = get_logger(__name__)


class SileroVad(ModelWrapper):
    """Warm Silero VAD model returning speech probability per audio window."""

    name = "silero-vad"

    def __init__(self) -> None:
        """Create the wrapper; the model is loaded lazily."""
        super().__init__()
        self._model: Any | None = None

    def _do_load(self) -> None:  # pragma: no cover - requires torch + silero
        """Load the Silero VAD model via torch.hub."""
        import torch

        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
        )
        self._model = model
        log.info("silero vad loaded")

    def reset(self) -> None:
        """Clear the model's recurrent state before a new audio stream.

        Silero VAD is an RNN that carries hidden state between calls. Without a
        reset at the start of each realtime session, stale state from a previous
        recording degrades detection on subsequent ones (speech can be missed
        entirely). No-op if the model hasn't been loaded yet.
        """
        if (
            self._loaded
            and self._model is not None
            and hasattr(self._model, "reset_states")
        ):
            self._model.reset_states()

    def speech_prob(
        self, window_pcm16: bytes, sample_rate: int
    ) -> float:  # pragma: no cover
        """Return the speech probability for a single audio window."""
        import torch

        self.load()
        assert self._model is not None
        import numpy as np

        audio = np.frombuffer(window_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio)
        return float(self._model(tensor, sample_rate).item())
