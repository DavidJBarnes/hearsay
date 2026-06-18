"""Engine placement: build the registry from configuration.

Each known engine has a capability spec. The placement map in
:class:`~hearsay_api.config.Settings` decides whether each is realized as a
:class:`LocalEngineClient` (GPU daemon) or a :class:`RunpodEngineClient`.
"""

from __future__ import annotations

from dataclasses import dataclass

from hearsay_api.config import EnginePlacement, Settings
from hearsay_api.engines.base import EngineRegistry
from hearsay_api.engines.local_client import LocalEngineClient
from hearsay_api.engines.runpod_client import RunpodEngineClient
from hearsay_api.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EngineSpec:
    """Declared capabilities of a known engine, independent of placement."""

    name: str
    supports_tts: bool = False
    supports_stt: bool = False
    supports_cloning: bool = False


ENGINE_SPECS: tuple[EngineSpec, ...] = (
    EngineSpec("kokoro", supports_tts=True),
    EngineSpec("chatterbox", supports_tts=True, supports_cloning=True),
    EngineSpec("faster-whisper", supports_stt=True),
    EngineSpec("pyannote", supports_stt=True),
)

# Map a request-facing model name to a registered engine name. Lets callers
# pass e.g. ``model="tts-1"`` or ``model="whisper-1"`` for OpenAI compatibility.
MODEL_ALIASES: dict[str, str] = {
    "tts-1": "kokoro",
    "tts-1-hd": "kokoro",
    "kokoro": "kokoro",
    "chatterbox": "chatterbox",
    "whisper-1": "faster-whisper",
    "faster-whisper": "faster-whisper",
    "large-v3": "faster-whisper",
}


def resolve_engine_name(model: str) -> str:
    """Resolve a request ``model`` to a registered engine name."""
    return MODEL_ALIASES.get(model, model)


def build_registry(settings: Settings) -> EngineRegistry:
    """Construct an :class:`EngineRegistry` honoring the placement config."""
    registry = EngineRegistry()
    for spec in ENGINE_SPECS:
        placement = settings.placement_for(spec.name)
        if placement is EnginePlacement.RUNPOD:
            log.info(
                "registering runpod engine",
                extra={"extra": {"engine": spec.name}},
            )
            registry.register(
                RunpodEngineClient(
                    spec.name,
                    endpoint=settings.runpod_endpoint,
                    api_key=settings.runpod_api_key,
                    supports_tts=spec.supports_tts,
                    supports_stt=spec.supports_stt,
                    supports_cloning=spec.supports_cloning,
                )
            )
        else:
            log.info(
                "registering local engine",
                extra={"extra": {"engine": spec.name}},
            )
            registry.register(
                LocalEngineClient(
                    spec.name,
                    base_url=settings.gpu_base_url,
                    timeout_s=settings.gpu_request_timeout_s,
                    supports_tts=spec.supports_tts,
                    supports_stt=spec.supports_stt,
                    supports_cloning=spec.supports_cloning,
                )
            )
    return registry
