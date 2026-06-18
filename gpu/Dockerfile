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

# The Ubuntu 22.04 CUDA base ships Python 3.10; pull 3.12 from deadsnakes and
# bootstrap pip for it. (ffmpeg/git are needed at runtime and install time.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        software-properties-common ca-certificates gnupg curl \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev ffmpeg git \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN python3.12 -m pip install --upgrade pip && python3.12 -m pip install .

COPY hearsay_gpu ./hearsay_gpu

EXPOSE 8001
CMD ["python3.12", "-m", "uvicorn", "hearsay_gpu.main:app", "--host", "0.0.0.0", "--port", "8001"]
