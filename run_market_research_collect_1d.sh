#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOCK_FILE="/tmp/market_research_collect_1d.lock"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python3}"
PIPELINE_SCRIPT="${PROJECT_DIR}/market_research_market_pipeline.py"

mkdir -p /home/user/logs

timestamp() {
  date -Is
}

echo "[$(timestamp)] market_research collect 1d: start"

if flock -E 99 -n "$LOCK_FILE" "$PYTHON_BIN" "$PIPELINE_SCRIPT" collect --interval 1d; then
  echo "[$(timestamp)] market_research collect 1d: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] market_research collect 1d: skipped, previous run still active"
    exit 0
  fi
  echo "[$(timestamp)] market_research collect 1d: failed with exit code $status" >&2
  exit "$status"
fi
