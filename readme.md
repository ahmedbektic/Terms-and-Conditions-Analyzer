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

- `c:\Users\bektic\code\Terms-and-Conditions-Analyzer`

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

### Option B: Manual Commands

Windows PowerShell:

1. Create/install Python env and backend deps:
   - `py -3.10 -m venv .venv`
   - `.\.venv\Scripts\python.exe -m pip install --upgrade pip`
   - `.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
2. Install frontend deps:
   - `npm install`
3. Start backend:
   - `.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000`
4. Start frontend in another terminal:
   - `npm exec -w frontend vite -- --host 127.0.0.1 --port 5173`

macOS/Linux:

1. Create/install Python env and backend deps:
   - `python3 -m venv .venv`
   - `./.venv/bin/python -m pip install --upgrade pip`
   - `./.venv/bin/python -m pip install -r backend/requirements.txt`
2. Install frontend deps:
   - `npm install`
3. Start backend:
   - `./.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000`
4. Start frontend in another terminal:
   - `npm exec -w frontend vite -- --host 127.0.0.1 --port 5173`

## Testing

Run all commands from repository root:

- `py -3.10 -m pytest backend/tests -q`
- `py -3.10 -m black --check backend`
- `npm run test:frontend`
- `npm run -w frontend test -- tests/auth.test.tsx` (single frontend test file)

## Code Quality Commands

Use these before opening a PR to match CI behavior.

Backend (Python):

- Auto-format: `py -3.10 -m black backend`
- Format check only: `py -3.10 -m black --check backend`
- Run tests: `py -3.10 -m pytest backend/tests -q`

Frontend (React/TypeScript):

- Lint check: `npm run lint:frontend`
- Lint autofix: `npm run -w frontend lint -- --fix`
- Run tests: `npm run test:frontend`

CI currently runs:

- Frontend: lint, build, test
- Backend: `black --check backend` and `pytest backend/tests`
- Extension: typecheck, test, build

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

Notes:

- If you hit extension-origin CORS issues, append
  `chrome-extension://<extension-id>` to `CORS_ALLOWED_ORIGINS` in `backend/.env`
  and restart backend.

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

The extension build reads Supabase auth config from one of these sources:

1. `EXTENSION_SUPABASE_URL` / `EXTENSION_SUPABASE_ANON_KEY` process env vars
2. fallback to frontend `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`

Optional explicit override before build:

```powershell
$env:EXTENSION_SUPABASE_URL="https://<your-project-ref>.supabase.co"
$env:EXTENSION_SUPABASE_ANON_KEY="<your-supabase-anon-key>"
npm run --prefix extension build
```

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
  - default fallback (if unset): `http://localhost:8000/api/v1`
  - set this when your backend is not at the default URL, or when you explicitly want `127.0.0.1`.
  - copy `frontend/.env.example` to `frontend/.env.local`, then edit as needed.
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Backend auth env vars:

- `AUTH_REQUIRE_JWT_SIGNATURE_VERIFICATION`
- `SUPABASE_JWT_AUDIENCE`
- `SUPABASE_JWT_ISSUER` (or `SUPABASE_URL` for derived issuer)
- `SUPABASE_JWT_JWKS_URL` (or derived from issuer)
- `SUPABASE_JWT_SECRET` (alternative to JWKS)

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
