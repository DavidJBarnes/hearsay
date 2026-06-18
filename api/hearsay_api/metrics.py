"""Prometheus metrics and GPU telemetry.

Exposes per-engine RTF (real-time factor) and TTFA (time-to-first-audio)
histograms, request latency, queue depth, and GPU memory/utilization gauges.
GPU stats are sampled lazily via ``pynvml`` when ``/metrics`` is scraped.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
)

from hearsay_api.logging import get_logger

log = get_logger(__name__)

REGISTRY = CollectorRegistry()

REQUEST_LATENCY = Histogram(
    "hearsay_request_latency_seconds",
    "End-to-end request latency.",
    labelnames=("route", "method"),
    registry=REGISTRY,
)

ENGINE_RTF = Histogram(
    "hearsay_engine_rtf",
    "Real-time factor (processing_time / audio_duration) per engine.",
    labelnames=("engine", "kind"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

ENGINE_TTFA = Histogram(
    "hearsay_engine_ttfa_seconds",
    "Time to first audio/transcript chunk per engine.",
    labelnames=("engine", "kind"),
    registry=REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "hearsay_queue_depth",
    "Number of jobs in each status.",
    labelnames=("status",),
    registry=REGISTRY,
)

GPU_MEM_USED = Gauge(
    "hearsay_gpu_memory_used_bytes",
    "GPU memory used per device.",
    labelnames=("device",),
    registry=REGISTRY,
)

GPU_MEM_TOTAL = Gauge(
    "hearsay_gpu_memory_total_bytes",
    "GPU memory total per device.",
    labelnames=("device",),
    registry=REGISTRY,
)

GPU_UTIL = Gauge(
    "hearsay_gpu_utilization_ratio",
    "GPU utilization ratio (0-1) per device.",
    labelnames=("device",),
    registry=REGISTRY,
)


def observe_rtf(engine: str, kind: str, processing_s: float, audio_s: float) -> None:
    """Record an RTF observation if ``audio_s`` is positive."""
    if audio_s > 0:
        ENGINE_RTF.labels(engine=engine, kind=kind).observe(processing_s / audio_s)


def observe_ttfa(engine: str, kind: str, seconds: float) -> None:
    """Record a time-to-first-chunk observation."""
    ENGINE_TTFA.labels(engine=engine, kind=kind).observe(seconds)


def set_queue_depth(counts: dict[str, int]) -> None:
    """Update the per-status queue-depth gauges."""
    for status_name, count in counts.items():
        QUEUE_DEPTH.labels(status=status_name).set(count)


class GpuSampler:
    """Samples GPU memory/utilization via pynvml, tolerant of absence."""

    def __init__(self, nvml: Any | None = None) -> None:
        """Create a sampler, optionally with an injected nvml module."""
        self._nvml = nvml
        self._initialized = False
        self._available = nvml is not None

    def _ensure_init(self) -> bool:
        """Lazily initialize pynvml; return availability."""
        if self._initialized:
            return self._available
        self._initialized = True
        if self._nvml is None:
            try:
                import pynvml  # type: ignore[import-untyped]

                self._nvml = pynvml
            except Exception:  # pragma: no cover - import failure path
                self._available = False
                return False
        try:
            self._nvml.nvmlInit()
            self._available = True
        except Exception:
            log.warning("pynvml init failed; GPU metrics disabled")
            self._available = False
        return self._available

    def sample(self) -> None:
        """Refresh the GPU gauges; no-op if NVML is unavailable."""
        if not self._ensure_init():
            return
        nvml = self._nvml
        assert nvml is not None
        count = nvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = nvml.nvmlDeviceGetHandleByIndex(i)
            mem = nvml.nvmlDeviceGetMemoryInfo(handle)
            util = nvml.nvmlDeviceGetUtilizationRates(handle)
            device = str(i)
            GPU_MEM_USED.labels(device=device).set(float(mem.used))
            GPU_MEM_TOTAL.labels(device=device).set(float(mem.total))
            GPU_UTIL.labels(device=device).set(float(util.gpu) / 100.0)


_sampler = GpuSampler()


def set_sampler(sampler: GpuSampler) -> None:
    """Replace the module-level GPU sampler (used by tests)."""
    global _sampler
    _sampler = sampler


def render_metrics() -> tuple[bytes, str]:
    """Sample GPU stats and return ``(body, content_type)`` for ``/metrics``."""
    _sampler.sample()
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
