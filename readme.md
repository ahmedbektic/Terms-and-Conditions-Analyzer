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

## Persistence Notes

In Postgres mode, the backend uses tables:

- `agreements`
- `reports`

## Documentation

See `docs/` for style and naming conventions.
For dashboard feature flow and extension seams, see `docs/dashboard-analysis-handoff.md`.
