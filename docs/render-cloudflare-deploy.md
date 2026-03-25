# Render + Cloudflare Workers Deployment Runbook

This runbook turns the repo into the deployment shape described in `DEPLOYMENT.md`:

- FastAPI backend on Render
- React frontend on Cloudflare Workers static assets
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
- `CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173[,chrome-extension://<your-extension-id>]`
- Rate-limit defaults are enabled in the backend; tune `API_RATE_LIMIT_*`, `AGREEMENT_CREATE_RATE_LIMIT_*`, and `ANALYSIS_*RATE_LIMIT*` in Render if your demo traffic needs a different budget.

Set these auth variables if you are not relying on the `SUPABASE_URL` derived defaults:

- `SUPABASE_JWT_ISSUER`
- `SUPABASE_JWT_JWKS_URL`
- `SUPABASE_JWT_AUDIENCE=authenticated`

Set these analysis variables only if you want hosted AI-backed analysis instead of deterministic mode:

- `ANALYSIS_PROVIDER_MODE=ai`
- `ANALYSIS_AI_PROVIDER_KIND=gemini` or `openai_compatible`
- `ANALYSIS_GEMINI_API_KEY` and `ANALYSIS_GEMINI_MODEL=gemini-2.5-flash`
- Optional Gemini budget overrides: `ANALYSIS_GEMINI_MAX_INPUT_TOKENS` and `ANALYSIS_GEMINI_ESTIMATED_CHARS_PER_TOKEN`
- `ANALYSIS_OPENAI_COMPATIBLE_API_KEY` and `ANALYSIS_OPENAI_COMPATIBLE_MODEL`

## Frontend on Cloudflare Workers

The frontend is deployed with `wrangler deploy`, not Cloudflare Pages. The `frontend/wrangler.jsonc` file now includes a Worker entrypoint that proxies `/api/*` traffic to Render while serving the SPA bundle from Cloudflare static assets.

Use these deployment/runtime inputs:

- Working directory: `frontend`
- Build command: `npm run build`
- Deploy command: `npm run deploy`
- Worker runtime variable: `API_BACKEND_ORIGIN=https://<your-render-service>.onrender.com`

Important:

- The browser app now defaults to the same-origin edge proxy at `/api/v1` when `VITE_API_BASE_URL` is unset in deployed builds.
- `API_BACKEND_ORIGIN` must point at the Render service origin without rewriting the `/api/v1` path segment.
- Local Vite dev still talks directly to `http://127.0.0.1:8000/api/v1` unless you override `VITE_API_BASE_URL`.

Set these Cloudflare Workers/Vite environment variables:

- `VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co`
- `VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>`
- Optional: `NODE_VERSION=22.16.0` or any version compatible with the repo's `>=20.19.0` requirement
- Optional browser override only if you intentionally want to bypass the edge proxy: `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api/v1`

Do not add a `_redirects` file for this Cloudflare deploy path. Current Wrangler/Workers SPA deploys already use `assets.not_found_handling = "single-page-application"`, and combining that with `/* /index.html 200` causes Cloudflare validation error `10021` for an infinite redirect loop.

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
- Cloudflare deploy succeeds and serves `frontend/dist`
- Cloudflare Worker runtime variable `API_BACKEND_ORIGIN` points at the Render backend origin
- Deployed browser requests hit `/api/v1/*` on the Cloudflare origin instead of calling Render directly
- Abuse-protection env vars are set to sane values for demo traffic and not disabled with `0`
- Supabase Auth redirect allow-list includes the Cloudflare Worker URL and any custom domain
- No `_redirects` file is being uploaded alongside a Wrangler SPA deploy

## Secret Handling

Do not commit real deployment secrets to the repo. Keep live values in:

- Render environment variables for backend secrets and backend runtime config
- Cloudflare Workers environment variables for `API_BACKEND_ORIGIN` and frontend build-time values
- Local untracked `.env` files only for local development

Cloudflare edge protections should still be layered on top of the app-level rate limits when you do a real deployment. The backend limits protect the API itself; Cloudflare remains the right place for broader bot/WAF controls at the edge.
