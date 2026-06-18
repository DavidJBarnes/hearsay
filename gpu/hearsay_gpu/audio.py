"""Audio encoding helpers for the GPU daemon.

Models emit float32 or int16 PCM; these helpers convert to WAV and other
container formats. WAV is produced in-process via the stdlib ``wave`` module;
compressed formats are produced with ffmpeg.
"""

from __future__ import annotations

import array
import io
import subprocess
import wave
from collections.abc import Callable, Sequence

from hearsay_gpu.logging import get_logger

log = get_logger(__name__)

# Subprocess runner indirection so tests can avoid spawning ffmpeg.
SubprocessRunner = Callable[[list[str], bytes], tuple[int, bytes, bytes]]


def floats_to_pcm16(samples: Sequence[float]) -> bytes:
    """Convert float samples in [-1, 1] to little-endian int16 PCM bytes."""
    out = array.array("h")
    for s in samples:
        clamped = max(-1.0, min(1.0, float(s)))
        out.append(int(clamped * 32767.0))
    return out.tobytes()


def pcm16_to_wav(pcm: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw int16 PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def _default_runner(argv: list[str], stdin: bytes) -> tuple[int, bytes, bytes]:
    """Run ``argv`` feeding ``stdin``; return ``(rc, stdout, stderr)``."""
    proc = subprocess.run(
        argv, input=stdin, capture_output=True, check=False
    )  # noqa: S603
    return proc.returncode, proc.stdout, proc.stderr


def encode(
    pcm: bytes,
    *,
    sample_rate: int,
    out_format: str,
    runner: SubprocessRunner | None = None,
) -> bytes:
    """Encode int16 PCM into ``out_format`` (wav/mp3/opus/flac/pcm)."""
    if out_format == "pcm":
        return pcm
    if out_format == "wav":
        return pcm16_to_wav(pcm, sample_rate=sample_rate)
    run = runner or _default_runner
    fmt_args = {
        "mp3": ["-f", "mp3"],
        "opus": ["-f", "opus"],
        "flac": ["-f", "flac"],
    }[out_format]
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        *fmt_args,
        "pipe:1",
    ]
    rc, stdout, stderr = run(argv, pcm)
    if rc != 0:
        raise RuntimeError(
            f"ffmpeg encode failed (rc={rc}): {stderr.decode('utf-8', 'replace')}"
        )
    return stdout
