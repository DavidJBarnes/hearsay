"""Hearsay GPU daemon.

A long-running internal service that loads Kokoro, faster-whisper, Chatterbox,
and (optionally) pyannote into VRAM and keeps them warm. The API gateway calls
it over internal HTTP (batch) and WebSocket (streaming).
"""

__version__ = "1.0.0"
