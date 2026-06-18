"""Hearsay API gateway package.

The public FastAPI gateway exposing OpenAI-compatible and native TTS/STT
endpoints, the Postgres-backed job queue worker, and the engine abstraction
that routes work to local (GPU daemon) or RunPod targets.
"""

__version__ = "1.0.0"
