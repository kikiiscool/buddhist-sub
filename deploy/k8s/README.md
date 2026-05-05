# Phase 2 — Kubernetes deployment

This directory holds production manifests. **Phase 1 (Apple M4 docker-compose)
must be working before you switch over.** The recommended layout:

```
namespace/buddhist-sub
├── postgres (pgvector/pgvector:pg16) + PVC
├── redis (bitnami/redis)
├── minio (or use cloud S3 directly)
├── backend Deployment + Service + Ingress (TLS)
├── worker-cpu  Deployment (RAG / Qwen-only steps)
├── worker-asr  Deployment with GPU node-selector (faster-whisper CUDA)
└── frontend Deployment + Service + Ingress
```

Key choices:

* **Whisper backend** in production = `faster-whisper` on a GPU node
  (`nvidia.com/gpu: 1`). Set `WHISPER_BACKEND=faster`,
  `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`.
* **Worker split**: ASR worker has GPU + only consumes `transcribe` queue;
  CPU worker handles `vad`, `dict_pass`, `rag_correct`, `srt`. Use Celery
  task routing to enforce.
* **Object storage**: replace MinIO with S3/R2/OSS in production by
  swapping the env vars; no code changes.
* **Database**: managed Postgres is fine but it MUST have `pgvector`
  extension (most providers support it).
* **HPA**: scale `worker-asr` on Celery queue length; scale `backend` on
  CPU/RPS.
* **Migrations**: run `alembic upgrade head` from an `initContainer` on the
  backend Deployment, and set `RUN_MIGRATIONS_ON_START=0` on the backend
  containers themselves so multiple replicas don't race to apply the same
  migration. See the `## DB migrations` section in the root README for the
  exact init container snippet.

Manifests will be added in Phase 2. For now, the docker-compose file is the
source of truth for env shape.
