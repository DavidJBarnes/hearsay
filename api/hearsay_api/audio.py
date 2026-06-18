"""Audio utilities: ffmpeg normalization and duration helpers.

The API normalizes STT inputs to 16 kHz mono signed-16-bit PCM before handing
audio to engines, and computes durations for artifact metadata and RTF. The
ffmpeg invocation is wrapped so tests can inject a fake runner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hearsay_api.logging import get_logger

log = get_logger(__name__)

# A runner takes argv + stdin bytes and returns (returncode, stdout, stderr).
Runner = Callable[[list[str], bytes], Awaitable[tuple[int, bytes, bytes]]]


async def _default_runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
    """Run ``argv`` feeding ``stdin``; return ``(rc, stdout, stderr)``."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=stdin)
    return proc.returncode or 0, stdout, stderr


async def to_pcm16k_mono(
    data: bytes, *, sample_rate: int = 16000, runner: Runner | None = None
) -> bytes:
    """Decode arbitrary audio ``data`` to raw mono PCM s16le at ``sample_rate``."""
    run = runner or _default_runner
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    rc, stdout, stderr = await run(argv, data)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed (rc={rc}): {stderr.decode('utf-8', 'replace')}")
    return stdout


def pcm_duration_s(pcm: bytes, *, sample_rate: int = 16000, sample_width: int = 2) -> float:
    """Return the duration in seconds of raw PCM ``pcm``."""
    frames = len(pcm) // sample_width
    if sample_rate <= 0:
        return 0.0
    return frames / sample_rate


async def transcode(data: bytes, *, out_format: str, runner: Runner | None = None) -> bytes:
    """Transcode ``data`` to ``out_format`` (wav/mp3/opus/flac) via ffmpeg."""
    run = runner or _default_runner
    fmt_args = {
        "wav": ["-f", "wav"],
        "mp3": ["-f", "mp3"],
        "opus": ["-f", "opus"],
        "flac": ["-f", "flac"],
        "pcm": ["-f", "s16le"],
    }[out_format]
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *fmt_args, "pipe:1"]
    rc, stdout, stderr = await run(argv, data)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed (rc={rc}): {stderr.decode('utf-8', 'replace')}")
    return stdout
