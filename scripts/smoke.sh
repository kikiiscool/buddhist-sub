#!/usr/bin/env bash
# End-to-end smoke test orchestrator.
#
# What it does:
#   1. docker compose up postgres / redis / minio
#   2. Install backend + worker (in-place, no venv) — uses current Python
#   3. Generate a 9-second silent test MP3 with ffmpeg
#   4. Start backend (uvicorn) and worker (celery) in background, with mock
#      Whisper / mock AI / mock RAG so no external API keys are needed
#   5. Run scripts/smoke_test.py against the API
#   6. Stream backend / worker logs, then tear everything down
#
# Designed to be runnable both locally (developer machine) and in CI
# (GitHub Actions ubuntu-latest).
#
# Pass --keep to skip teardown for debugging.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/.smoke-logs"
AUDIO="${SMOKE_AUDIO:-$ROOT/.smoke-logs/sample.mp3}"
KEEP="0"
for arg in "$@"; do
  [[ "$arg" == "--keep" ]] && KEEP="1"
done

mkdir -p "$LOG_DIR"

# ---- env shared by backend + worker ------------------------------------------
export POSTGRES_USER="${POSTGRES_USER:-buddhist}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-buddhist_dev_pw}"
export POSTGRES_DB="${POSTGRES_DB:-buddhist_sub}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/1}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/2}"
export S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
export S3_BUCKET="${S3_BUCKET:-buddhist-sub}"
export S3_REGION="${S3_REGION:-us-east-1}"

# Worker-only — required by pydantic-settings even in mock mode.
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-mock-not-used}"
export WHISPER_BACKEND="${WHISPER_BACKEND:-mock}"
export WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-yue}"
export MOCK_AI="${MOCK_AI:-1}"
export EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-dashscope}"  # value ignored when MOCK_AI=1

PIDS=()
cleanup() {
  echo "[smoke] -- cleanup --"
  set +e
  for pid in "${PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  if [[ "$KEEP" != "1" ]]; then
    (cd "$ROOT" && docker compose down -v) >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[smoke] root=$ROOT logs=$LOG_DIR"
cd "$ROOT"

# ---- 1) infra ----------------------------------------------------------------
echo "[smoke] starting infra (postgres, redis, minio)"
docker compose up -d postgres redis minio minio-init >"$LOG_DIR/compose-up.log" 2>&1

echo "[smoke] waiting for postgres / redis / minio to be healthy"
for i in {1..60}; do
  pg=$(docker inspect -f '{{.State.Health.Status}}' buddhist_postgres 2>/dev/null || echo missing)
  rd=$(docker inspect -f '{{.State.Health.Status}}' buddhist_redis 2>/dev/null || echo missing)
  mn=$(docker inspect -f '{{.State.Health.Status}}' buddhist_minio 2>/dev/null || echo missing)
  echo "[smoke]  postgres=$pg redis=$rd minio=$mn"
  if [[ "$pg" == "healthy" && "$rd" == "healthy" && "$mn" == "healthy" ]]; then break; fi
  sleep 2
done

# ---- 2) install backend + worker --------------------------------------------
PIP_FLAGS="${PIP_FLAGS:--q}"
echo "[smoke] installing backend"
python -m pip install $PIP_FLAGS -e ./backend
echo "[smoke] installing worker"
python -m pip install $PIP_FLAGS -e ./worker

# ---- 3) generate sample audio ------------------------------------------------
if [[ ! -f "$AUDIO" ]]; then
  echo "[smoke] generating sample MP3 → $AUDIO"
  ffmpeg -y -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=16000" \
         -t 9 -c:a libmp3lame -b:a 64k "$AUDIO" >/dev/null 2>&1
fi
ls -la "$AUDIO"

# ---- 4) start backend + worker ----------------------------------------------
echo "[smoke] starting backend (uvicorn) → $LOG_DIR/backend.log"
( cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 ) \
  >"$LOG_DIR/backend.log" 2>&1 &
PIDS+=("$!")

echo "[smoke] starting worker (celery) → $LOG_DIR/worker.log"
( cd worker && python -m celery -A worker.celery_app:celery_app worker --loglevel=info --concurrency=1 ) \
  >"$LOG_DIR/worker.log" 2>&1 &
PIDS+=("$!")

# wait for backend /healthz
echo "[smoke] waiting for backend /healthz"
for i in {1..60}; do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "[smoke] backend up"
    break
  fi
  sleep 1
  if [[ $i -eq 60 ]]; then
    echo "[smoke] backend never came up" >&2
    tail -200 "$LOG_DIR/backend.log" >&2 || true
    exit 11
  fi
done

# ---- 5) run driver -----------------------------------------------------------
set +e
python "$ROOT/scripts/smoke_test.py" "$AUDIO" --api http://localhost:8000
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "[smoke] === backend.log (tail) ==="
  tail -100 "$LOG_DIR/backend.log" || true
  echo "[smoke] === worker.log (tail) ==="
  tail -100 "$LOG_DIR/worker.log" || true
fi

exit $RC
