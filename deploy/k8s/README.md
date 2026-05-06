# Phase 2 — Kubernetes deployment

Production manifests for the buddhist-sub stack. Layered with kustomize so
you can keep the base manifests pristine and apply environment-specific
patches via overlays.

```
deploy/k8s/
├── base/                       # canonical manifests
│   ├── 00-namespace.yaml
│   ├── 10-configmap.yaml       # non-secret env (S3 host, model name, …)
│   ├── 11-secrets.example.yaml # SAMPLE — copy & fill, never commit real keys
│   ├── 20-postgres.yaml        # pgvector/pgvector:pg16 StatefulSet
│   ├── 21-redis.yaml
│   ├── 22-minio.yaml           # + bucket-init Job
│   ├── 30-backend.yaml         # FastAPI Deployment with `migrate` initContainer
│   ├── 31-worker.yaml          # generic Celery worker
│   ├── 32-worker-asr.yaml      # GPU-only ASR worker template (DISABLED — see file)
│   ├── 33-frontend.yaml
│   ├── 40-ingress.yaml         # TLS via cert-manager
│   ├── 41-hpa.yaml             # HPAs + KEDA-based queue-length example
│   └── kustomization.yaml
└── overlays/
    ├── dev/                    # 1 replica, floating `:dev` tag, Always pull
    └── prod/                   # pinned tag, real hostnames, secret merge
```

---

## Quick deploy (dev cluster)

```bash
# 1. Build + push images. Replace REPLACE_OWNER with your registry org.
export REPO=ghcr.io/REPLACE_OWNER
docker build -t $REPO/buddhist-sub-backend:dev  ./backend
docker build -t $REPO/buddhist-sub-worker:dev   ./worker
docker build -t $REPO/buddhist-sub-frontend:dev ./frontend
docker push $REPO/buddhist-sub-backend:dev
docker push $REPO/buddhist-sub-worker:dev
docker push $REPO/buddhist-sub-frontend:dev

# 2. Edit registry path in deploy/k8s/base/kustomization.yaml (or use
#    `kustomize edit set image` inside the overlay you're using).
#    Edit the hostnames in deploy/k8s/base/40-ingress.yaml.

# 3. Create real secrets (DO NOT COMMIT).
cp deploy/k8s/base/11-secrets.example.yaml deploy/k8s/base/11-secrets.yaml
$EDITOR deploy/k8s/base/11-secrets.yaml          # fill in real values
echo "deploy/k8s/base/11-secrets.yaml" >> .git/info/exclude  # local ignore

# 4. Apply.
kubectl apply -k deploy/k8s/overlays/dev
```

Production:

```bash
kubectl apply -k deploy/k8s/overlays/prod
```

Use a secret manager (External Secrets / Sealed Secrets / SOPS) instead of
checking in `11-secrets.yaml` for real prod.

---

## Day-2 ops

### Apply migrations manually (alternative to initContainer)

If you'd rather run migrations from CI instead of from an `initContainer`:

```bash
kubectl run -it --rm migrate \
  --image=$REPO/buddhist-sub-backend:TAG \
  --namespace=buddhist-sub \
  --env-from=configmap/buddhist-sub-config \
  --env-from=secret/buddhist-sub-secrets \
  -- alembic upgrade head
```

Then set `RUN_MIGRATIONS_ON_START=0` in the ConfigMap (already the default
in this repo) and remove the `initContainers` block from
`30-backend.yaml`.

### CBETA ingestion (one-shot Job)

```bash
kubectl run -it --rm cbeta-ingest \
  --image=$REPO/buddhist-sub-backend:TAG \
  --namespace=buddhist-sub \
  --env-from=configmap/buddhist-sub-config \
  --env-from=secret/buddhist-sub-secrets \
  -- python /app/scripts/ingest_cbeta.py --canons T,X
```

(scripts/ are not currently in the backend image — add `COPY scripts ./scripts`
to `backend/Dockerfile` if you want this pattern, or run from a separate
ingestion image.)

### Scaling

* `kubectl get hpa -n buddhist-sub` — current replica targets.
* For better worker scaling, install [KEDA](https://keda.sh/) and replace the
  CPU-based worker HPA with the `redis`-trigger ScaledObject in
  `41-hpa.yaml`'s comment block.

---

## Architecture decisions

### Why an `initContainer` for alembic?

Multi-replica backends would otherwise race to apply the same migration —
historically a source of partial schema, deadlock, and mysterious 5xx
spikes during deploys. With this pattern:

* Migrations run **exactly once per rollout**, before any new replica
  starts.
* Backend containers have `RUN_MIGRATIONS_ON_START=0` so they NEVER attempt
  migrations themselves.
* Migration failure → rollout fails fast, old replicas keep serving.

### Why is `worker-asr` disabled?

Splitting transcription onto a GPU node only pays off once Celery task
routing is in place. Currently `pipeline.run_job` orchestrates every step
in a single task — there's no individual `transcribe` task to route. The
`32-worker-asr.yaml` template is committed with `# DISABLED:` line prefixes
so it's literally a copy-paste-and-uncomment once the routing refactor
lands. Tracked as a follow-up.

### Whisper backend in production

* **CPU worker** (default): `WHISPER_BACKEND=faster`, CPU mode. Good enough
  for moderate throughput; acceptable cost.
* **GPU worker** (after routing refactor): same image rebuilt with
  `--build-arg WHISPER_EXTRA=faster` against a CUDA base, plus
  `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`. ~5× faster than
  CPU on similar-tier hardware.
* **Apple M-series dev** (`mlx-whisper`): not in the container — Metal
  isn't available inside a Linux container. Run that worker natively on
  the host while the rest of the stack runs in Docker (see root README).

### Storage

* In-cluster MinIO is fine for staging / single-tenant. For real prod use
  S3 / R2 / GCS / Aliyun OSS — delete `22-minio.yaml`, set
  `S3_ENDPOINT` / `S3_BUCKET` / `S3_REGION` in the ConfigMap, and put
  `S3_ACCESS_KEY` / `S3_SECRET_KEY` in the Secret.
* Postgres: managed providers (RDS, Cloud SQL, Aiven) MUST support the
  `vector` and `pg_trgm` extensions. Most do. Verify before deploying.

---

## Known gaps / follow-ups

| | Item |
|---|---|
| ⏳ | Celery task routing refactor → enables `worker-asr` GPU split |
| ⏳ | KEDA scaling on Redis queue length (template in `41-hpa.yaml`) |
| ⏳ | Network policies (deny-all default + allow specific service-to-service) |
| ⏳ | PodDisruptionBudgets for backend / worker / postgres |
| ⏳ | Pod security admission (`restricted`) |
| ⏳ | Backups: Postgres `pg_dump` CronJob + MinIO replication / lifecycle |
| ⏳ | Observability: ServiceMonitor / Loki annotations / OpenTelemetry sidecar |
| ⏳ | CI image-build pipeline (build-push to GHCR on tag) |
