# GitHub 直接部署（Web）

如果你想「直接喺 GitHub 推上去就自動 deploy」，而家可以用 repo 入面嘅 workflow：

- `.github/workflows/frontend-deploy.yml`

## 做一次設定（5-10 分鐘）

1. 去 Vercel 建立/匯入 `frontend/` project。
2. 喺 GitHub repo `Settings -> Secrets and variables -> Actions` 新增：
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
3. 在 Vercel 設定 Frontend 環境變數（最少）：
   - `NEXT_PUBLIC_API_BASE`（例：`https://your-api-domain`）

## Workflow 行為

- 開 PR：只會跑 `frontend` build，幫你擋壞 code。
- merge / push 到 `main`：先 build，成功後自動 deploy 去 Vercel production。

## 建議 backend / worker 部署

呢個 workflow 目前先處理前端（最快上線方式）。

後端與 worker 可以用以下策略：
- Backend（FastAPI）→ Render / Fly.io / Railway（掛 managed Postgres + Redis + S3）
- Worker（Celery）→ 同平台開 background worker service
- Storage → S3/R2/OSS

如果你想，我下一步可以直接幫你補：
- `backend` Docker deploy workflow
- `worker` deploy workflow
- 以及一份一鍵 `.env` 對照表
