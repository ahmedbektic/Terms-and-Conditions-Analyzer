# Render + Cloudflare Pages Deployment Runbook

This runbook turns the repo into the deployment shape described in `DEPLOYMENT.md`:

- FastAPI backend on Render
- React frontend on Cloudflare Pages
- Supabase for Postgres and auth

## Backend on Render

The repo now includes `render.yaml` for the backend service definition.
Use `backend/.env.production.example` as the reference sheet when you populate Render's environment variables.

Use these settings when you create the Blueprint-backed service:

- Service: `terms-and-conditions-analyzer-api`
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Set these Render environment variables before first real use:

- `PERSISTENCE_BACKEND=postgres`
- `SUPABASE_DATABASE_URL=<your-supabase-postgres-connection-string>` or `DATABASE_URL=...`
- `SUPABASE_URL=https://<your-project-ref>.supabase.co`
- `CORS_ALLOWED_ORIGINS=https://<your-project>.pages.dev[,https://<your-custom-domain>]`

Set these auth variables if you are not relying on the `SUPABASE_URL` derived defaults:

- `SUPABASE_JWT_ISSUER`
- `SUPABASE_JWT_JWKS_URL`
- `SUPABASE_JWT_AUDIENCE=authenticated`

Set these analysis variables only if you want hosted AI-backed analysis instead of deterministic mode:

- `ANALYSIS_PROVIDER_MODE=ai`
- `ANALYSIS_AI_PROVIDER_KIND=gemini` or `openai_compatible`
- `ANALYSIS_GEMINI_API_KEY` and `ANALYSIS_GEMINI_MODEL`
- `ANALYSIS_OPENAI_COMPATIBLE_API_KEY` and `ANALYSIS_OPENAI_COMPATIBLE_MODEL`

## Frontend on Cloudflare Pages

Use the repository root as the Pages root directory so Pages builds against the workspace lockfile.

Recommended Pages settings:

- Framework preset: `React (Vite)` or `None`
- Root directory: repository root
- Build command: `npm ci && npm run build:frontend`
- Build output directory: `frontend/dist`

Set these Cloudflare Pages environment variables:

- `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api/v1`
- `VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co`
- `VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>`
- Optional: `NODE_VERSION=22.16.0` or any version compatible with the repo's `>=20.19.0` requirement

The frontend includes `frontend/public/_redirects` with `/* /index.html 200`, so direct navigation stays on the SPA entrypoint after deploy.

## Local Production Preview

From the repo root:

```bash
npm run build:frontend
npm run -w frontend preview -- --host 127.0.0.1 --port 4173
```

Use `frontend/.env.production.example` as the reference if you want to create a local `frontend/.env.production` file for that preview.

## Cross-Service Checklist

Before calling the deployment done, verify all of this:

- Render health check responds at `/health`
- Cloudflare Pages build succeeds and serves `frontend/dist`
- `VITE_API_BASE_URL` points at the Render backend, not localhost
- Render `CORS_ALLOWED_ORIGINS` includes every deployed frontend origin
- Supabase Auth redirect allow-list includes the Cloudflare Pages URL and any custom domain

## Secret Handling

Do not commit real deployment secrets to the repo. Keep live values in:

- Render environment variables for backend secrets and backend runtime config
- Cloudflare Pages environment variables for frontend build-time values
- Local untracked `.env` files only for local development
