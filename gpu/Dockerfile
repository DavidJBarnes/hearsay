# Hearsay GPU daemon image.
#
# Uses an NVIDIA CUDA runtime base so faster-whisper (CTranslate2), Kokoro,
# Chatterbox, and pyannote can run on the host GPU. Requires the NVIDIA
# Container Toolkit on the host (see docker-compose.yml `deploy.resources`).
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip3 install --upgrade pip && pip3 install .

COPY hearsay_gpu ./hearsay_gpu

EXPOSE 8001
CMD ["uvicorn", "hearsay_gpu.main:app", "--host", "0.0.0.0", "--port", "8001"]
