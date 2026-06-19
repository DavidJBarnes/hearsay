"""Tests for model wrapper base classes and the gated diarizer."""

from __future__ import annotations

import pytest

from hearsay_gpu.config import GpuSettings
from hearsay_gpu.models import diarization
from hearsay_gpu.models.base import ModelWrapper, Segment
from hearsay_gpu.models.chatterbox_model import ChatterboxModel


class CountingModel(ModelWrapper):
    """A wrapper counting how many times it loads."""

    name = "counting"

    def __init__(self) -> None:
        super().__init__()
        self.loads = 0

    def _do_load(self) -> None:
        self.loads += 1


def test_load_is_idempotent() -> None:
    """``load`` only loads the underlying model once."""
    model = CountingModel()
    assert model.is_loaded is False
    model.load()
    model.load()
    assert model.loads == 1
    assert model.is_loaded is True


def test_vad_reset() -> None:
    """VAD reset is a no-op until loaded, then clears recurrent state."""
    from hearsay_gpu.models.vad import SileroVad

    class FakeSilero:
        def __init__(self) -> None:
            self.resets = 0

        def reset_states(self) -> None:
            self.resets += 1

    vad = SileroVad()
    vad.reset()  # not loaded yet -> no-op, no error
    fake = FakeSilero()
    vad._model = fake
    vad._loaded = True
    vad.reset()
    assert fake.resets == 1


def test_segment_as_dict() -> None:
    """Segment serialization omits speaker when unset."""
    assert Segment(0.0, 1.0, "hi").as_dict() == {"start": 0.0, "end": 1.0, "text": "hi"}
    with_speaker = Segment(0.0, 1.0, "hi", speaker="S0").as_dict()
    assert with_speaker["speaker"] == "S0"


def test_chatterbox_make_embedding() -> None:
    """Chatterbox embedding metadata records the reference size."""
    meta = ChatterboxModel().make_embedding(b"abcd")
    assert meta["engine"] == "chatterbox"
    assert meta["reference_bytes"] == 4


def test_chatterbox_reference_path() -> None:
    """The reference helper returns None or writes a temp WAV file."""
    from pathlib import Path

    model = ChatterboxModel()
    assert model._reference_path(None) is None
    path = model._reference_path(b"\x00\x00" * 100)
    assert path is not None
    data = Path(path).read_bytes()
    assert data[:4] == b"RIFF"
    Path(path).unlink()


def test_diarizer_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Diarization raises when disabled."""
    monkeypatch.setattr(
        diarization, "get_gpu_settings", lambda: GpuSettings(diarization_enabled=False)
    )
    with pytest.raises(diarization.DiarizationUnavailableError, match="disabled"):
        diarization.Diarizer().diarize(b"\x00\x00")


def test_diarizer_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Diarization raises when enabled without an HF token."""
    monkeypatch.setattr(
        diarization,
        "get_gpu_settings",
        lambda: GpuSettings(diarization_enabled=True, hf_token=None),
    )
    with pytest.raises(diarization.DiarizationUnavailableError, match="HF_TOKEN"):
        diarization.Diarizer().diarize(b"\x00\x00")


def test_diarizer_enabled_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """When enabled with a token, diarize delegates to the pipeline runner."""
    monkeypatch.setattr(
        diarization,
        "get_gpu_settings",
        lambda: GpuSettings(diarization_enabled=True, hf_token="hf_x"),
    )
    d = diarization.Diarizer()
    monkeypatch.setattr(
        d, "_run", lambda pcm: [{"start": 0.0, "end": 1.0, "speaker": "A"}]
    )
    turns = d.diarize(b"\x00\x00")
    assert turns[0]["speaker"] == "A"
