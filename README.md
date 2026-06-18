# Hearsay

A fully self-hosted, open-weight **text-to-speech and speech-to-text platform**.
You bring a GPU; Hearsay gives you an OpenAI-compatible speech API, voice
cloning, batch jobs, and live microphone transcription — with **all inference
running locally**, no third-party speech services involved. The architecture is
built to burst overflow work to RunPod later; v1 ships the local path fully
working and the RunPod target wired but stubbed.

What you get out of the box:

- A drop-in OpenAI-compatible `/v1/audio/speech` + `/v1/audio/transcriptions` API.
- A web console for synthesis, transcription, voice cloning, jobs, and metrics.
- Warm models held in VRAM for low latency, behind a clean engine abstraction.

- **TTS** — [Kokoro](https://github.com/hexgrad/kokoro) (default, preset voices,
  warm, < 1 GB) with streaming output, and [Chatterbox](https://github.com/resemble-ai/chatterbox)
  (MIT, voice cloning + emotion, on demand) powering the cloning flow.
- **STT** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) large-v3
  (warm, FP16; switchable to `large-v3-turbo` / INT8).
- **Realtime STT** — VAD-segmented rolling buffer over WebSocket emitting
  incremental partial + final transcripts.
- **Diarization** — [pyannote](https://github.com/pyannote/pyannote-audio),
  config-gated and **off by default** (needs an HF token).
- **OpenAI-compatible** `/v1/audio/speech` and `/v1/audio/transcriptions` so
  existing clients work unchanged.

## Architecture

Two FastAPI processes plus Postgres and a React console:

```
┌────────────┐    REST/WS    ┌─────────────┐   HTTP/WS    ┌──────────────┐
│  frontend  │ ───────────▶  │  api gateway │ ──────────▶ │  gpu daemon  │
│ (React/TS) │               │  (FastAPI)   │             │ warm models  │
└────────────┘               └──────┬───────┘             │  in VRAM     │
                                    │                      └──────────────┘
                              ┌─────▼──────┐
                              │  Postgres  │  jobs / voices / transcripts
                              └────────────┘
```

- The **`api`** gateway is the public surface: REST + WebSocket, business logic,
  DB, the Postgres-backed job queue worker, Alembic migrations, and the
  **engine abstraction**.
- The **`gpu`** daemon holds Kokoro / faster-whisper / Chatterbox / pyannote
  warm in VRAM and never reloads them between requests. It is internal-only.

Everything routes through the `Engine` interface and an `EngineRegistry`. The
`ENGINE_PLACEMENT` config maps each engine → `local` (the GPU daemon) or
`runpod`. `LocalEngineClient` calls the daemon; `RunpodEngineClient` is fully
defined but stubbed in v1 (raises `NotImplementedError` with a clear message).

## Run it

### Requirements

- Docker + Docker Compose.
- An NVIDIA GPU plus the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  on the host (the `gpu` service needs CUDA). Target hardware is a single
  RTX 3090 (24 GB) — all warm models co-reside with headroom.
- First boot downloads model weights, so it takes a few minutes.

### Start the stack

```bash
cp .env.example .env
# set HEARSAY_BOOTSTRAP_API_KEY to your own key (default works for local use)
docker compose up --build
```

This starts Postgres, the GPU daemon, the API gateway (migrations auto-apply on
boot), and the console:

| Service  | URL                              | Notes                          |
|----------|----------------------------------|--------------------------------|
| Console  | http://localhost:5173            | the web UI                     |
| API      | http://localhost:8000            | `/healthz`, `/readyz`, `/metrics` |
| GPU      | internal only (`gpu:8001`)       | warm models                    |

### Verify it's up

```bash
curl http://localhost:8000/healthz   # {"status":"ok"}
curl http://localhost:8000/readyz    # DB + engines registered, "ready": true
```

The gateway's `/readyz` covers database connectivity and the engine registry; the
GPU daemon reports its own model-loading readiness at `gpu:8001/readyz` (internal).
The very first synthesis or transcription may be slower while a model warms up.

Then open the console, paste your API key (the bootstrap key from `.env`) into the
top bar, and use the **TTS Playground**, **Speech to Text** (file + live mic),
**Voice Library**, **Jobs**, and **Metrics** tabs.

## API surface

OpenAI-compatible:

```bash
# Text to speech
curl -s http://localhost:8000/v1/audio/speech \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"kokoro","voice":"af_heart","input":"Hello from Hearsay."}' \
  --output hello.wav

# Transcription
curl -s http://localhost:8000/v1/audio/transcriptions \
  -H "Authorization: Bearer $KEY" \
  -F file=@hello.wav -F model=whisper-1
```

Native:

- `GET/POST/DELETE /v1/voices` — list/create/delete; POST with a reference
  sample triggers Chatterbox cloning.
- `GET/POST/DELETE /v1/jobs` — batch TTS/STT jobs with status + results.
- `WS /v1/realtime?api_key=...&model=faster-whisper` — live mic STT
  (incremental + final transcripts).
- `GET /metrics` — Prometheus (per-engine RTF, TTFA, request latency, queue
  depth, GPU memory/utilization via `pynvml`).
- `GET /healthz`, `GET /readyz`.

All `/v1/*` routes require an `Authorization: Bearer <key>` API key. Keys are
stored only as SHA-256 hashes; the bootstrap key is auto-provisioned on startup.

## Configuration

All configuration is environment-driven (see `.env.example` for the complete,
documented set). Highlights:

- `HEARSAY_ENGINE_PLACEMENT` — JSON map of engine → `local` | `runpod`.
- `HEARSAY_WHISPER_MODEL` / `HEARSAY_GPU_WHISPER_MODEL` — STT model id.
- `HEARSAY_STORAGE_BACKEND` — `local` disk (default) or `s3` (MinIO-compatible).
- `HEARSAY_DIARIZATION_ENABLED` (+ `HEARSAY_HF_TOKEN`) — gated, off by default.
- `HEARSAY_RUNPOD_ENDPOINT` / `HEARSAY_RUNPOD_API_KEY` — present but unused in v1.

## Development & tests

Backend (`api`) — 100% unit-test coverage is enforced:

```bash
cd api
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                 # runs with --cov-fail-under=100
ruff check . && black --check hearsay_api && mypy hearsay_api
```

GPU daemon (`gpu`):

```bash
cd gpu && pip install -e '.[dev]'
PYTHONPATH=. pytest
```

Frontend (`frontend`):

```bash
cd frontend && npm install
npm test        # vitest component + unit tests
npm run build   # type-check + production build
```

## Storage layout

All audio is addressed by an opaque `ref` and accessed only through the
`StorageBackend` abstraction (`LocalDiskBackend` default, `S3Backend`
optional) — paths are never hardcoded. TTS outputs land under
`jobs/<id>/output.<fmt>`; cloned-voice references under `voices/<id>/reference`.

## Notes on the RunPod stub

`RunpodEngineClient` implements the full `Engine` interface but every capability
raises `NotImplementedError` with guidance. Route an engine to it by setting
that engine to `"runpod"` in `HEARSAY_ENGINE_PLACEMENT`. This is the single
intentional stub in v1; everything else is fully implemented.
