"""Tests for configuration loading and helpers."""

from __future__ import annotations

from hearsay_api.config import (
    EnginePlacement,
    Settings,
    StorageBackendKind,
    get_settings,
)


def test_placement_for_default() -> None:
    """Unknown engines default to local placement."""
    s = Settings()
    assert s.placement_for("kokoro") is EnginePlacement.LOCAL
    assert s.placement_for("does-not-exist") is EnginePlacement.LOCAL


def test_placement_parsed_from_json_string() -> None:
    """A JSON string env value is parsed into the placement map."""
    s = Settings(engine_placement='{"chatterbox": "runpod"}')  # type: ignore[arg-type]
    assert s.placement_for("chatterbox") is EnginePlacement.RUNPOD


def test_placement_accepts_dict() -> None:
    """A dict value is accepted unchanged."""
    s = Settings(engine_placement={"kokoro": EnginePlacement.RUNPOD})
    assert s.placement_for("kokoro") is EnginePlacement.RUNPOD


def test_storage_backend_enum_default() -> None:
    """Storage backend defaults to local."""
    assert Settings().storage_backend is StorageBackendKind.LOCAL


def test_get_settings_is_cached() -> None:
    """``get_settings`` returns a cached singleton."""
    get_settings.cache_clear()
    assert get_settings() is get_settings()
