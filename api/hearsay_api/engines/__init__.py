"""Engine abstraction package.

Everything that performs speech work routes through the :class:`Engine`
interface and the :class:`EngineRegistry`. Placement config decides whether a
given engine is served by the local GPU daemon or bursted to RunPod.
"""

from hearsay_api.engines.base import (
    Engine,
    EngineRegistry,
    SynthesisResult,
    TranscriptionResult,
)

__all__ = [
    "Engine",
    "EngineRegistry",
    "SynthesisResult",
    "TranscriptionResult",
]
