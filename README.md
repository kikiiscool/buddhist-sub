# 佛法字幕生成器 · Buddhist Dharma Subtitle Generator

由 Google Colab notebook (Whisper large + Cantonese) 升級成完整 web app:
**MP3 → VAD 切段 → Whisper → 詞典預處理 → Qwen + CBETA RAG 校正 → 人工 review → SRT**。

每一步都可監控、可暫停、可重做、可手動修改。

---

## 架構

```
┌─────────────┐   HTTP/WS    ┌──────────────┐   Redis    ┌──────────────┐
│  Next.js    │◀────────────▶│  FastAPI     │◀──────────▶│  Celery      │
│  Frontend   │              │  Backend     │  pub/sub   │  Worker(s)   │
└─────────────┘              └──────────────┘            └──────┬───────┘
       │                            │                           │
       │ presigned PUT              │                           │
       ▼                            ▼                           ▼
   ┌────────┐                  ┌──────────┐               ┌──────────┐
   │ MinIO  │                  │ Postgres │◀─pgvector─────│  CBETA   │
   │  (S3)  │                  │          │               │  ingest  │
   └────────┘                  └──────────┘               └──────────┘
```

* **frontend/** — Next.js 14 App Router + Tailwind. Upload + per-step progress + subtitle editor + WebSocket event log.
* **backend/** — FastAPI + SQLAlchemy(async) + WebSocket. Issues presigned uploads, manages jobs, relays Redis pub/sub events.
* **worker/** — Celery. Pluggable Whisper backend (`mlx` / `faster` / `openai`). Qwen via DashScope OpenAI-compatible API. RAG against CBETA chunks in pgvector.
* **scripts/ingest_cbeta.py** — Sparse-clones `cbeta-org/xml-p5`, parses TEI → plain text → embeds → pgvector.
* **data/dictionaries/buddhist_terms.json** — Whisper Cantonese 常見錯字對照表 (rule-based pre-pass, 慳 LLM token)。
* **data/prompts/** — Whisper `initial_prompt` (粵語佛教詞彙 hot-words) + Qwen 校正 system prompt。

---

## Phase 1 — 喺 Apple M4 跑

**前置:**

* macOS 13+,Apple Silicon (M1/M2/M3/M4)
* Python 3.11+, Node 20+, Docker Desktop
* `ffmpeg` (`brew install ffmpeg`)
* 一個 [DashScope API key](https://dashscope.console.aliyun.com/) (Qwen + embedding)

### 1. 啟動 infra

```bash
cp .env.example .env
# 編輯 .env,填入 DASHSCOPE_API_KEY
docker compose up -d postgres redis minio minio-init
```

> MinIO 連線提示：
> - `http://localhost:9000` 係 **S3 API endpoint**（俾程式用，唔係管理介面）。
> - `http://localhost:9001` 先係 **MinIO Console UI**（瀏覽器應該開呢個）。
> - 如果見到 `ERR_CONNECTION_REFUSED`，先檢查 Docker 有冇起到：
>
> ```bash
> docker compose ps
> docker compose logs --tail=100 minio minio-init
> ```

### 2. CBETA 入庫 (一次性,可後台)

```bash
cd scripts
python -m venv .venv && source .venv/bin/activate
pip install psycopg2-binary pgvector openai python-dotenv
# 完整大正藏 + 卍續藏 ~1-2 小時 (視 DashScope rate limit)
python ingest_cbeta.py --canons T,X
# 想快測試:--limit-works 50
```

### 3. Backend (native)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

預設 lifespan 會喺啟動時自動跑 `alembic upgrade head`,所以 dev 上 zero-config。
詳情見下面 [DB migrations](#db-migrations) 一節。

> 如果你淨係想喺無 Postgres/Redis/MinIO 嘅環境 smoke-test backend 啟動，
> 可以臨時用 `SKIP_DB_INIT=1` 跳過啟動時 DB 初始化：
>
> ```bash
> SKIP_DB_INIT=1 uvicorn app.main:app --reload
> ```

### 4. Worker (native,M4 用 mlx-whisper)

```bash
cd worker
python -m venv .venv && source .venv/bin/activate
pip install -e ".[mlx]"      # 喺 M4 安裝 mlx-whisper
celery -A worker.celery_app:celery_app worker --loglevel=info --concurrency=1
```

> **點解 worker 唔入 Docker?** mlx-whisper 用 Apple Metal,Linux container 行唔到。
> Docker 入面只放 stateful infra (Postgres / Redis / MinIO),worker 喺 host 跑最快。

### 5. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

### 6. 試跑

1. 上傳一條粵語佛法 MP3
2. 睇住 6 步 pipeline 嘅進度條同 WebSocket event 流即時更新
3. 第 5 步 (review) 自動暫停 — 喺 UI 改字幕,然後撳「繼續」
4. 第 6 步生成 SRT,撳「下載 SRT」攞檔

---

## 常見：`ERR_CONNECTION_REFUSED` /「無法連線至這個網站」

如果你開 `localhost` 見到連線被拒絕，通常係服務未起好，或者開錯 port：

| 服務 | 正確網址 | 用途 |
|---|---|---|
| Frontend | `http://localhost:3000` | Web UI |
| Backend | `http://localhost:8000/docs` | API Swagger |
| MinIO API | `http://localhost:9000` | S3 endpoint（程式用，唔係管理頁） |
| MinIO Console | `http://localhost:9001` | MinIO 管理介面（瀏覽器要開呢個） |

快速檢查（建議照順序）：

```bash
# 1) infra 有冇起到
docker compose ps

# 2) MinIO / Postgres / Redis log 有冇 error
docker compose logs --tail=100 minio minio-init postgres redis

# 3) backend health check
curl -i http://localhost:8000/healthz
```

如果你只係 smoke-test backend 啟動（無 DB/Redis/MinIO），用：

```bash
SKIP_DB_INIT=1 uvicorn app.main:app --reload
```

但注意：呢個模式只保證 backend process 起得嚟；涉及資料庫嘅 API（例如 `/jobs`）仍然會因為無 Postgres 而失敗。

---

## DB migrations

Schema 由 alembic 管理,migration 喺 `backend/alembic/versions/`。

### 啟動時行為 (兩個 env flag 控制)

| `SKIP_DB_INIT` | `RUN_MIGRATIONS_ON_START` | 結果 |
|---|---|---|
| `1` | _(any)_ | 完全唔掂 DB (純 import smoke / 無 Postgres 環境) |
| `0` (default) | `1` (default) | lifespan 自動跑 `alembic upgrade head` |
| `0` | `0` | 假設有人預先 apply 咗 migration (production / k8s init container) |

### 日常 workflow

```bash
cd backend

# 改完 model 之後 (autogenerate 草稿)
alembic revision --autogenerate -m "add foo column"
# *** review backend/alembic/versions/<id>_add_foo_column.py ***
# 特別小心 enum 改動同 server_default

# 套用最新 migration
alembic upgrade head

# 退一步
alembic downgrade -1

# 睇 history / current
alembic history
alembic current
```

### Production 部署 pattern

```yaml
# k8s 例子 — backend Deployment 加 init container
spec:
  template:
    spec:
      initContainers:
        - name: migrate
          image: ghcr.io/.../buddhist-sub-backend:TAG
          command: ["alembic", "upgrade", "head"]
          envFrom: [{secretRef: {name: backend-secrets}}]
      containers:
        - name: backend
          env:
            - name: RUN_MIGRATIONS_ON_START
              value: "0"   # 多 replica 時必須關,避免 race
```

### 注意事項

* `0001_initial` 會 `CREATE EXTENSION vector / pg_trgm` — managed Postgres
  通常容許,但部分 sandbox 唔得,要 ops 預先安裝。
* `cbeta_chunks` table 由 `scripts/ingest_cbeta.py` 用 raw SQL 創建 (因為佢用
  `vector(1024)` 列,alembic 唔認 pgvector type)。`alembic/env.py` 嘅
  `include_object` filter 將佢排除喺 autogenerate 之外,唔會被誤刪。
* 改 enum 值 (例如加 `StepName`) **唔好**用 autogenerate 嘅 default 輸出,
  Postgres 嘅 `ALTER TYPE ... ADD VALUE` 唔可以喺 transaction 入面跑;要寫
  `with op.get_context().autocommit_block(): op.execute("ALTER TYPE ...")`。

---

## 暫停 / 修改 / 重做

| 動作 | 點做 |
|------|------|
| 暫停某步 | UI 撳「暫停」 → worker 喺下個 chunk 邊界檢查 status,停低 |
| 繼續 | UI 撳「繼續」 → worker poll 到 status=running,繼續 |
| 重做某步 | UI 撳「重做」 → backend re-enqueue `pipeline.run_step` task |
| 跳過 review | UI 撳「跳過」 → status=skipped,直接行去下一步 |
| 改字幕 | review 階段點任何一段,即場 textarea 編輯,存咗會 mark `edited_by_human` |
| 改詞典 | 編輯 `data/dictionaries/buddhist_terms.json`,然後重做 `dict_pass` 步 |

---

## 整個 pipeline 嘅優化點 (已內建)

1. **Whisper `initial_prompt` 餵粵語佛教詞彙** — 大幅減少同音錯字 (data/prompts/whisper_initial_cantonese.txt)
2. **VAD 預切** — silero-vad 切到 sentence boundary,避免 Whisper 將兩句黐埋,同時可並行轉錄
3. **`word_timestamps=True`** — 校正後仍可重組準確時軸
4. **`condition_on_previous_text=False`** — 避免 Whisper hallucination 滾雪球
5. **Rule-based 詞典 pre-pass** — deterministic、零成本,慳 LLM token
6. **CBETA RAG** — Qwen 校正時帶最相關嘅經文段落,專名/引文準
7. **DashScope OpenAI-compatible API** — 同個 SDK 跑 Qwen + embedding,prompt cache 可以 hit
8. **校正帶前後 context** — 唔會斷章取意
9. **JSON 輸出 + 低 temperature** — Qwen 結果穩定可解析
10. **Pause/resume 細粒度到 chunk 邊界** — 改錯就暫停,唔使重頭跑

---

## Phase 2 roadmap — Kubernetes

見 [`deploy/k8s/README.md`](deploy/k8s/README.md)。重點:

* `WHISPER_BACKEND=faster` + GPU node (`nvidia.com/gpu: 1`)
* Worker 分兩個 Deployment:`worker-asr` (GPU only, 食 transcribe queue) 同 `worker-cpu` (其他 step)
* Postgres 換成 managed (要支援 pgvector),MinIO 換成 S3/R2/阿里 OSS
* HPA 按 Celery queue length scale `worker-asr`

---

## 之後可以加

* **Speaker diarization** (pyannote) — 多人對話時標記講者
* **Diff view** — 一齊睇 raw / dict / AI / final 四欄
* **批次上傳** — 一次過丟 10 條 MP3 入 queue
* **詞典自學** — 用戶手改嘅修正自動 propose 加入 `buddhist_terms.json`
* **講者風格適配** — 每個法師 fine-tune 一個 LoRA / 詞典
* **YouTube/Bilibili 字幕直接 push** (透過 OAuth API)
