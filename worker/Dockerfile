# Worker image — generic CPU build.
#
# In production:
#   * For an ASR-dedicated GPU worker, build with --build-arg WHISPER_EXTRA=faster
#     and deploy on a GPU node (set WHISPER_BACKEND=faster, WHISPER_DEVICE=cuda).
#   * For a CPU-only "everything else" worker, the default args are fine.
#
# Apple Silicon dev (mlx-whisper) intentionally does NOT run in this image —
# mlx requires Metal which is unavailable in Linux containers. Run that worker
# natively on the host.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      ffmpeg \
      libsndfile1 \
      curl \
  && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first to avoid pulling the 2GB CUDA wheel from PyPI.
# A GPU image should override this layer with a CUDA-capable torch build.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --upgrade pip && \
    pip install --extra-index-url ${TORCH_INDEX} torch==2.3.1 torchaudio==2.3.1

COPY pyproject.toml ./
# WHISPER_EXTRA: empty (default) | faster | openai-asr
ARG WHISPER_EXTRA=
RUN if [ -n "${WHISPER_EXTRA}" ]; then \
      pip install -e ".[${WHISPER_EXTRA}]"; \
    else \
      pip install -e .; \
    fi

COPY worker ./worker

# Default to a sensible non-GPU configuration; overridden by the k8s manifest.
ENV WHISPER_BACKEND=faster \
    CELERY_WORKER_CONCURRENCY=1

CMD ["celery", "-A", "worker.celery_app:celery_app", "worker", \
     "--loglevel=info", "--concurrency=1"]
