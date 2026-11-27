# Deployment guide

| Component | Platform |
|---|---|
| Frontend | Vercel |
| API + Celery worker | Render (`render.yaml` Blueprint) |
| PostgreSQL, Auth, Realtime, Storage | Supabase |
| Redis | Upstash |
| WhatsApp | Meta Cloud API |

Order: Supabase → Upstash → Render → Vercel → back to Render for CORS → Meta webhook.

## 1. Supabase
Follow [SUPABASE_CONFIGURATION.md](SUPABASE_CONFIGURATION.md). Keep the session-pooler `DATABASE_URL`, project URL, anon key and service-role key.

## 2. Upstash Redis
Create a Redis database in the region closest to Render. Copy the TLS URL and append the certificate requirement Celery expects:
```
rediss://default:<password>@<host>.upstash.io:6379?ssl_cert_reqs=required
```
This is `REDIS_URL`.

## 3. Render (API + worker)
1. Push the repository to GitHub.
2. In Render, go to **New → Blueprint** and select the repo. `render.yaml` creates:
   - `smart-queue-api`: a web service that runs `alembic upgrade head` before each deploy (`preDeployCommand`) and serves `uvicorn` with a health check at `/api/health`
   - `smart-queue-worker`: a background worker that runs Celery with embedded beat (`-B`), which sends messages and runs the 30 s outbox sweep. Run **only one** worker with `-B`.
3. Fill in the secret variables Render prompts for. They're listed in [backend/.env.example](../backend/.env.example). `PUBLIC_APP_URL` and `CORS_ORIGINS` are the Vercel URL, so set them after step 4 and redeploy.
4. If your Render plan doesn't support `preDeployCommand`, run `alembic upgrade head` from a Render shell or your machine before deploying.
5. Create the first restaurant and owner from a Render shell: `python -m app.scripts.bootstrap ...` (see the README).

## 4. Vercel (frontend)
1. **New Project** → import the repo → set **Root Directory** to `frontend`. Vercel detects Vite: build `npm run build`, output `dist`.
2. Environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (the Render API URL).
3. `vercel.json` rewrites every path to `index.html`, so `/manager/...` and `/menu/<slug>` work on refresh.
4. Put the Vercel URL into Render's `CORS_ORIGINS` and `PUBLIC_APP_URL`, and into Supabase Auth → Site URL.

## 5. WhatsApp
Follow [WHATSAPP_INTEGRATION.md](WHATSAPP_INTEGRATION.md): get the templates approved, set the env vars on **both** Render services, register the webhook, then enable WhatsApp in Settings.

## Checklist after deploy
- `GET https://<api>/api/health` → `{"status":"ok"}`
- The owner logs in and lands on the Queue Manager Dashboard. A waiter account lands on the Waiter Dashboard.
- Register a test customer (consent ticked, your own number). The menu message shows *Sent*, then *Delivered*.
- With two browsers (manager and waiter): mark a table available, and both update without refresh.
- `/menu/<slug>` opens on a phone without signing in.

## Operations notes
- **Secrets** live only in Render, Vercel and Supabase dashboards. `.env` files are git-ignored.
- **Scaling:** the API is stateless, so add instances freely. Allocation correctness comes from DB locks, not process count. Add extra Celery workers *without* `-B`.
- **Backups:** Supabase daily backups. Allocation history and activity logs are never deleted by the app.
- **Local Windows note:** `celery worker -B` is not supported on Windows. Run `celery beat` as a separate process and use `--pool=solo` for the worker.
