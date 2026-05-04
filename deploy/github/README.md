# GitHub 直接部署（Web）

而家 repo 已經有兩條 GitHub Actions pipeline：

- `.github/workflows/frontend-deploy.yml`：Frontend CI + Vercel production deploy
- `.github/workflows/backend-worker-ci.yml`：Backend / Worker Python CI smoke checks

## 1) Frontend 自動部署（Vercel）

### 一次性設定

1. 去 Vercel 建立/匯入 `frontend/` project。
2. 喺 GitHub repo `Settings -> Secrets and variables -> Actions` 新增：
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
3. 在 Vercel 設定 Frontend 環境變數：
   - `NEXT_PUBLIC_API_BASE`（例：`https://api.your-domain.com`）

### 觸發規則

- PR（有 frontend 變更）：會跑 build
- push `main`（有 frontend 變更）：build 成功後 deploy 到 Vercel production

## 2) Backend / Worker CI（GitHub）

`backend-worker-ci.yml` 會喺 PR 同 `main` push 自動執行：

- `pip install -e .`
- import smoke test（backend: `app.main`、worker: `worker.tasks`）

用途：喺 merge 前先擋住依賴壞掉或基本 import error。

## 3) Production `.env` 模板

參考檔案：

- `deploy/github/env.production.example`

你可以用佢做基礎，再填返你實際平台（Render/Fly.io/Railway/K8s）嘅 host、key、bucket。
