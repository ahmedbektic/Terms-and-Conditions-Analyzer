#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-help}"
TARGET="${2:-all}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

show_usage() {
  cat <<'EOF'
Usage:
  ./scripts/dev.sh run docker
  ./scripts/dev.sh run preview
  ./scripts/dev.sh rebuild extension
  ./scripts/dev.sh rebuild docker
EOF
}

run_in_repo() {
  (
    cd "${REPO_ROOT}"
    "$@"
  )
}

case "${ACTION}" in
  help)
    show_usage
    ;;
  run)
    case "${TARGET}" in
      docker)
        run_in_repo docker compose up
        ;;
      preview)
        run_in_repo npm run preview:frontend
        ;;
      *)
        echo "Unsupported run target '${TARGET}'. Use: docker or preview." >&2
        exit 1
        ;;
    esac
    ;;
  rebuild)
    case "${TARGET}" in
      extension)
        run_in_repo npm install --prefix extension --no-audit --no-fund
        ;;
      docker)
        run_in_repo docker compose build backend frontend
        ;;
      *)
        echo "Unsupported rebuild target '${TARGET}'. Use extension or docker." >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unsupported action '${ACTION}'. Use run, rebuild, or help." >&2
    exit 1
    ;;
esac
