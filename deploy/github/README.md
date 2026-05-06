# GitHub 直接部署（Web）

而家 repo 已經有兩條 GitHub Actions pipeline：

- `.github/workflows/frontend-deploy.yml`：Frontend CI + Vercel production deploy
- `.github/workflows/backend-worker-ci.yml`：Backend / Worker Python CI smoke checks

## 1) Frontend 自動部署（Vercel）

**預設關閉**。只跑 build,唔會 deploy,所以未配置 Vercel 嘅 repo 唔會次次
push 都紅 X。要開啟,做齊以下三步:

### 一次性設定

1. 去 Vercel 建立/匯入 `frontend/` project。
2. 喺 GitHub repo `Settings → Secrets and variables → Actions` 嘅
   **Secrets** tab 新增：
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
3. 同一頁嘅 **Variables** tab 新增 (注意係 variable,唔係 secret)：
   - `ENABLE_VERCEL_DEPLOY` = `true`
4. 在 Vercel 設定 Frontend 環境變數：
   - `NEXT_PUBLIC_API_URL`（例：`https://api.your-domain.com`）
   - `NEXT_PUBLIC_WS_URL`（例：`wss://api.your-domain.com`）

要關返,將 `ENABLE_VERCEL_DEPLOY` 設做 `false` 或者直接刪走呢個 variable 即可。

### 觸發規則

- PR（有 frontend 變更）：會跑 build
- push `main`（有 frontend 變更）：build 成功 + `ENABLE_VERCEL_DEPLOY=true`
  → deploy 到 Vercel production
- 其他情況下 deploy job 會被 skip（綠色 dash,唔會 fail）

## 2) Backend / Worker CI（GitHub）

`backend-worker-ci.yml` 會喺 PR 同 `main` push 自動執行：

- `pip install -e .`
- import smoke test（backend: `app.main`、worker: `worker.tasks`）

用途：喺 merge 前先擋住依賴壞掉或基本 import error。

## 3) Production `.env` 模板

參考檔案：

- `deploy/github/env.production.example`

你可以用佢做基礎，再填返你實際平台（Render/Fly.io/Railway/K8s）嘅 host、key、bucket。
