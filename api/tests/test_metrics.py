"""Tests for the metrics module and GPU sampler."""

from __future__ import annotations

from typing import Any

from hearsay_api import metrics


def test_observe_helpers_run() -> None:
    """RTF/TTFA/queue helpers update without error."""
    metrics.observe_rtf("kokoro", "tts", 0.5, 1.0)
    metrics.observe_rtf("kokoro", "tts", 0.5, 0.0)  # ignored (no audio)
    metrics.observe_ttfa("kokoro", "tts", 0.1)
    metrics.set_queue_depth({"queued": 2, "running": 1})


class FakeMem:
    """Fake NVML memory info."""

    used = 1024
    total = 24 * 1024


class FakeUtil:
    """Fake NVML utilization rates."""

    gpu = 42


class FakeNvml:
    """A fake pynvml module."""

    def __init__(self, *, fail_init: bool = False) -> None:
        self.fail_init = fail_init

    def nvmlInit(self) -> None:
        if self.fail_init:
            raise RuntimeError("no gpu")

    def nvmlDeviceGetCount(self) -> int:
        return 1

    def nvmlDeviceGetHandleByIndex(self, i: int) -> int:
        return i

    def nvmlDeviceGetMemoryInfo(self, handle: int) -> FakeMem:
        return FakeMem()

    def nvmlDeviceGetUtilizationRates(self, handle: int) -> FakeUtil:
        return FakeUtil()


def test_gpu_sampler_samples() -> None:
    """The sampler reads device stats and sets gauges."""
    sampler = metrics.GpuSampler(nvml=FakeNvml())
    sampler.sample()
    sampler.sample()  # second call hits the already-initialized branch
    assert metrics.GPU_UTIL.labels(device="0")._value.get() == 0.42


def test_gpu_sampler_init_failure() -> None:
    """A failed NVML init disables sampling gracefully."""
    sampler = metrics.GpuSampler(nvml=FakeNvml(fail_init=True))
    sampler.sample()  # should not raise
    assert sampler._available is False


def test_gpu_sampler_default_imports_pynvml() -> None:
    """A default sampler imports pynvml and disables itself without a GPU."""
    sampler = metrics.GpuSampler()
    sampler.sample()  # imports pynvml, nvmlInit fails (no GPU) -> disabled
    assert sampler._initialized is True
    assert sampler._available is False
    sampler.sample()  # already initialized + unavailable -> early return


def test_render_metrics_uses_sampler() -> None:
    """``render_metrics`` invokes the sampler and returns Prometheus text."""
    called: dict[str, Any] = {}

    class CountingSampler(metrics.GpuSampler):
        def sample(self) -> None:
            called["sampled"] = True

    metrics.set_sampler(CountingSampler(nvml=FakeNvml()))
    body, content_type = metrics.render_metrics()
    assert called["sampled"] is True
    assert b"hearsay_request_latency" in body or b"hearsay_" in body
    assert "text/plain" in content_type
