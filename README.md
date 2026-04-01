# AI Terms & Conditions Analyzer and Change Tracker

An AI-powered web app and browser extension that helps users understand terms and conditions, track what they agreed to, and review analysis reports over time.

## Overview

This project provides:

- terms submission from a dashboard
- automated analysis summary, flagged clauses, and trust score
- saved report history for later review

## Current Stack

- Frontend: React + TypeScript (Vite dev server)
- Backend: FastAPI
- Persistence:
  - in-memory (default)
  - Postgres/Supabase (optional via env config)

## Local Setup

All commands below are run from the repository root:

### Option A: Use Scripts (recommended)

Windows PowerShell:

1. `.\scripts\bootstrap.ps1`
2. `.\scripts\run-backend.ps1`
3. In a second terminal: `.\scripts\run-frontend.ps1`

macOS/Linux:

1. `bash ./scripts/bootstrap.sh`
2. `bash ./scripts/run-backend.sh`
3. In a second terminal: `bash ./scripts/run-frontend.sh`

Open the app at:

- `http://127.0.0.1:5173`

Bootstrap notes:

- The bootstrap scripts install backend Python dependencies, root/frontend npm dependencies, and extension npm dependencies.
- If you only need to refresh backend deps, use `./scripts/bootstrap.ps1 -SkipNpm` or `./scripts/bootstrap.sh --skip-npm`.

### Option B: Manual Commands

Windows PowerShell:

1. Create/install Python env and backend deps:
   - `py -3.10 -m venv .venv`
   - `.\.venv\Scripts\python.exe -m pip install --upgrade pip`
   - `.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
2. Install frontend deps:
   - `npm install`
3. Install extension deps:
   - `npm install --prefix extension --no-audit --no-fund`
4. Start backend:
   - `.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000`
5. Start frontend in another terminal:
   - `npm exec -w frontend dev -- --host 127.0.0.1 --port 5173`

macOS/Linux:

1. Create/install Python env and backend deps:
   - `python3 -m venv .venv`
   - `./.venv/bin/python -m pip install --upgrade pip`
   - `./.venv/bin/python -m pip install -r backend/requirements.txt`
2. Install frontend deps:
   - `npm install`
3. Install extension deps:
   - `npm install --prefix extension --no-audit --no-fund`
4. Start backend:
   - `./.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000`
5. Start frontend in another terminal:
   - `npm run -w frontend dev -- --host 127.0.0.1 --port 5173`

## Unified Dev Helpers

Use these wrappers when you want one stable entrypoint instead of remembering individual commands.

PowerShell:

- `./scripts/dev.ps1 help`
- `./scripts/dev.ps1 run backend`
- `./scripts/dev.ps1 run frontend`
- `./scripts/dev.ps1 run preview`
- `./scripts/dev.ps1 run docker`
- `./scripts/dev.ps1 rebuild backend`
- `./scripts/dev.ps1 rebuild frontend`
- `./scripts/dev.ps1 rebuild extension`
- `./scripts/dev.ps1 rebuild all`
- `./scripts/dev.ps1 rebuild docker`

Git Bash / macOS / Linux:

- `./scripts/dev.sh help`
- `./scripts/dev.sh run backend`
- `./scripts/dev.sh run frontend`
- `./scripts/dev.sh run preview`
- `./scripts/dev.sh run docker`
- `./scripts/dev.sh rebuild backend`
- `./scripts/dev.sh rebuild frontend`
- `./scripts/dev.sh rebuild extension`
- `./scripts/dev.sh rebuild all`
- `./scripts/dev.sh rebuild docker`

## Command Reference

Assume Git Bash on Windows unless noted otherwise. Run commands from the repository root.

### Formatting and Linting

- Backend format:
  - `./.venv/Scripts/python.exe -m black backend`
- Backend format check:
  - `./.venv/Scripts/python.exe -m black --check backend`
- Frontend lint:
  - `npm run lint:frontend`
- Extension typecheck:
  - `npm run typecheck:extension`

### Tests

- Backend test suite:
  - `./.venv/Scripts/python.exe -m pytest backend/tests -q`
- Frontend test suite:
  - `npm run test:frontend`
- Extension test suite:
  - `npm run test:extension`
- Full repo verification sequence:
  - `./.venv/Scripts/python.exe -m black --check backend`
  - `npm run lint:frontend`
  - `./.venv/Scripts/python.exe -m pytest backend/tests -q`
  - `npm run test:frontend`
  - `npm run typecheck:extension`
  - `npm run test:extension`
  - `docker compose config`

### Builds

- Frontend build:
  - `npm run build:frontend`
- Frontend local production preview:
  - `npm run preview:frontend`
- Extension build:
  - `npm run build:extension`
- Backend local build-equivalent smoke check:
  - `./.venv/Scripts/python.exe -m compileall backend/app`
- Docker builds:
  - `docker compose build backend`
  - `docker compose build frontend`
  - `docker compose build backend frontend`

### Local Deployment

- Backend only:
  - `./scripts/dev.sh run backend`
- Frontend only:
  - `./scripts/dev.sh run frontend`
- Frontend preview against local assets/worker runtime:
  - `./scripts/dev.sh run preview`
- Dockerized local frontend + backend:
  - `./scripts/dev.sh run docker`
- Direct Docker commands:
  - `docker compose up`
  - `docker compose up --build`
  - `docker compose down`

CI currently runs:

- Tooling/infrastructure: `docker compose config`, Bash helper syntax check, PowerShell helper smoke run
- Frontend: lint, build, test
- Backend: `black --check backend` and `pytest backend/tests`
- Extension: typecheck, test, build

## Deployment

Render + Cloudflare Workers deployment is wired around:

- `render.yaml` for the backend blueprint
- `frontend/wrangler.jsonc` plus `frontend/worker/index.ts` for the Cloudflare edge proxy/static frontend
- `backend/.env.production.example` for backend production env reference values
- `frontend/.env.production.example` for production env reference values

Use `docs/render-cloudflare-deploy.md` for the exact setup steps, required environment variables, and verification flow.

## Browser Extension Local Runtime Testing (SCRUM-9)

Detailed guide:

- `extension/README.md` (see `Local Runtime Test (End-to-End)`)

Quick path (PowerShell, from repo root):

1. Start backend + frontend:
   - `.\scripts\run-backend.ps1`
   - `.\scripts\run-frontend.ps1`
2. Build extension:
   - `npm install --prefix extension`
   - `npm run --prefix extension build`
3. Load unpacked extension from `extension/` in `chrome://extensions`.
4. Ensure Supabase redirect allow list includes `https://<extension-id>.chromiumapp.org/supabase-auth`.
   - Google provider must be enabled in Supabase Auth for the current environment.
   - Setup matrix: `docs/google-auth-setup-matrix.md`.
5. Open extension popup and use `Log in` (Google OAuth).
6. Open a policy page, click extension icon, then click `Analyze page`.
7. Do not manually seed `chrome.storage.local.auth_session`; runtime auth writes session state after successful popup sign-in.

Notes:

- If you hit extension-origin CORS issues, append
  `chrome-extension://<extension-id>` to `CORS_ALLOWED_ORIGINS` in `backend/.env`
  and restart backend.
- If extension analysis fails with network/permission errors, also verify the
  backend host is present in extension `manifest.json` `host_permissions`.

## Local Google Auth Env Checklist (Web + Extension)

Use this exact env baseline for local OAuth verification.

### 1) Backend `backend/.env`

```env
PERSISTENCE_BACKEND=memory
AUTH_REQUIRE_JWT_SIGNATURE_VERIFICATION=true
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_JWT_AUDIENCE=authenticated
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

If extension analyze calls fail with CORS, append extension origin:

```env
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,chrome-extension://<your-extension-id>
```

Restart backend after editing `backend/.env`.

### 2) Frontend `frontend/.env.local`

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

### 3) Extension auth config

The extension build reads auth/API config from these sources:

1. process env (`EXTENSION_*`, then `VITE_*`)
2. extension env files (`extension/.env`, `extension/.env.local`)
3. frontend env files (`frontend/.env`, `frontend/.env.local`) as fallback
4. API fallback default only: `http://127.0.0.1:8000/api/v1`

Optional explicit override before build:

```powershell
$env:EXTENSION_API_BASE_URL="http://127.0.0.1:8000/api/v1"
$env:EXTENSION_SUPABASE_URL="https://<your-project-ref>.supabase.co"
$env:EXTENSION_SUPABASE_ANON_KEY="<your-supabase-anon-key>"
npm run --prefix extension build
```

Optional runtime override for debugging (service-worker console):

```javascript
await chrome.storage.local.set({
  api_base_url: 'http://127.0.0.1:8000/api/v1',
  extraction_min_length: 160,
});
```

`extraction_min_length` is intentionally dev-oriented; keep it a positive integer.

### 4) Required Supabase redirect allow-list entries

In Supabase Auth URL configuration, include:

- `http://127.0.0.1:5173`
- `http://localhost:5173`
- `https://<extension-id>.chromiumapp.org/supabase-auth`

Google provider setup details and redirect matrix:

- `docs/google-auth-setup-matrix.md`

## Environment Configuration

See:

- `backend/.env.example`

Key backend env vars:

- `PERSISTENCE_BACKEND` = `memory` or `postgres`
- `SUPABASE_DATABASE_URL` (preferred Postgres URI)
- `DATABASE_URL` (fallback Postgres URI)
- `POSTGRES_AUTO_CREATE_SCHEMA` = `true`/`false`

Frontend optional env var:

- `VITE_API_BASE_URL`
  - default fallback (if unset): `http://127.0.0.1:8000/api/v1`
  - set this when your backend is not at the default URL, or when you explicitly want `127.0.0.1`.
  - copy `frontend/.env.example` to `frontend/.env.local`, then edit as needed.
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Backend auth/runtime env vars:

- `AUTH_REQUIRE_JWT_SIGNATURE_VERIFICATION`
- `SUPABASE_JWT_AUDIENCE`
- `SUPABASE_JWT_ISSUER` (or `SUPABASE_URL` for derived issuer)
- `SUPABASE_JWT_JWKS_URL` (or derived from issuer)
- `SUPABASE_JWT_SECRET` (alternative to JWKS)
- `ANALYSIS_PROVIDER_MODE` (`deterministic` default, `ai` for AI-backed mode)
- `ANALYSIS_AI_PROVIDER_KIND` (`gemini` default, or `openai_compatible`)
- `ANALYSIS_GEMINI_API_KEY` and `ANALYSIS_GEMINI_MODEL` (Gemini mode, `gemini-2.5-flash` recommended)
- `ANALYSIS_GEMINI_MAX_INPUT_TOKENS` and `ANALYSIS_GEMINI_ESTIMATED_CHARS_PER_TOKEN` (Gemini prompt budget guard)
- `ANALYSIS_OPENAI_COMPATIBLE_API_KEY` and `ANALYSIS_OPENAI_COMPATIBLE_MODEL` (OpenAI-compatible mode)
- `ANALYSIS_AI_FALLBACK_TO_DETERMINISTIC` (`true` recommended)
- `ANALYSIS_EXECUTION_MODE` (`sync` active; seam for future queued/worker mode)

## Persistence Notes

In Postgres mode, the backend uses tables:

- `agreements`
- `reports`

## Documentation

See `docs/` for style and naming conventions.
For dashboard feature flow and extension seams, see `docs/dashboard-analysis-handoff.md`.
For auth boundaries and ownership semantics, see `docs/auth-architecture-scrum11.md`.
For SCRUM-9 extension implementation status and explicit unfinished areas, see `docs/scrum-9-handoff-post-implementation.md`.
For Google provider enablement and redirect setup across web + extension, see `docs/google-auth-setup-matrix.md`.
