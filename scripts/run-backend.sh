#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
ENV_FILE="${REPO_ROOT}/backend/.env"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Missing virtual environment Python at ${VENV_PYTHON}. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  "${VENV_PYTHON}" -m uvicorn app.main:app --app-dir "${REPO_ROOT}/backend" --reload --env-file "${ENV_FILE}" --host 127.0.0.1 --port 8000
else
  echo "Warning: backend/.env not found. Using process environment only." >&2
  "${VENV_PYTHON}" -m uvicorn app.main:app --app-dir "${REPO_ROOT}/backend" --reload --host 127.0.0.1 --port 8000
fi

