#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${HOME:-/home/user}"
PYTHON_BIN="${PYTHON_BIN:-${USER_HOME}/trading_venv/bin/python3}"
SCRIPT="${PROJECT_DIR}/warmup_rag_cache.py"
LOG_DIR="${USER_HOME}/logs"

mkdir -p "$LOG_DIR"

if [ -f "${USER_HOME}/.env.trading" ]; then
  set -a
  source "${USER_HOME}/.env.trading"
  set +a
fi

timestamp() {
  date -Is
}

echo "[$(timestamp)] Warmup RAG Cache: start"

if "$PYTHON_BIN" "$SCRIPT"; then
  echo "[$(timestamp)] Warmup RAG Cache: success"
else
  status=$?
  echo "[$(timestamp)] Warmup RAG Cache: failed with exit code $status" >&2
  exit "$status"
fi
