#!/usr/bin/env bash
set -euo pipefail

SKIP_NPM="false"
if [[ "${1:-}" == "--skip-npm" ]]; then
  SKIP_NPM="true"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PATH="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_PATH}/bin/python"

echo "Repository root: ${REPO_ROOT}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Creating virtual environment at ${VENV_PATH}"
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv "${VENV_PATH}"
  else
    python -m venv "${VENV_PATH}"
  fi
fi

echo "Installing backend Python dependencies"
"${VENV_PYTHON}" -m pip install --upgrade pip
"${VENV_PYTHON}" -m pip install -r "${REPO_ROOT}/backend/requirements.txt"
"${VENV_PYTHON}" -m pip install pytest black

if [[ "${SKIP_NPM}" == "false" ]]; then
  echo "Installing frontend/workspace npm dependencies"
  (
    cd "${REPO_ROOT}"
    npm install
    echo "Installing extension npm dependencies"
    npm install --prefix extension --no-audit --no-fund
  )
else
  echo "Skipping npm install"
fi

echo "Bootstrap complete."
echo "Backend run command:"
echo "\"${VENV_PYTHON}\" -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000"
echo "Frontend run command:"
echo "npm run -w frontend dev -- --host 127.0.0.1 --port 5173"
echo "Frontend production preview command:"
echo "npm run -w frontend preview -- --host 127.0.0.1 --port 4173"
echo "Extension build command:"
echo "npm run --prefix extension build"
