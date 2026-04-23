#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <job_name> <script_path> [script_args...]" >&2
  exit 64
fi

JOB_NAME="$1"
SCRIPT_PATH="$2"
shift 2

LOCK_FILE="/tmp/postmarket_${JOB_NAME}.lock"
USER_HOME="${HOME:-/home/user}"
PYTHON_BIN="${PYTHON_BIN:-${USER_HOME}/trading_venv/bin/python}"
INFISICAL_BIN="${INFISICAL_BIN:-${PROJECT_DIR}/run_infisical_quiet.sh}"
INFISICAL_PROJECT_ID="${INFISICAL_PROJECT_ID:-1d44cf0c-94b5-4e64-bccd-9c4da8843fec}"
INFISICAL_ENV="${INFISICAL_ENV:-dev}"
JOB_TIMEOUT_SECONDS="${POSTMARKET_AI_TIMEOUT_SECONDS:-1800}"
KILL_AFTER_SECONDS="${POSTMARKET_AI_KILL_AFTER_SECONDS:-30}"
export AI_COST_GUARD_ENABLED="${AI_COST_GUARD_ENABLED:-1}"
export AI_MAX_FALLBACKS_DAILY_REPORT="${AI_MAX_FALLBACKS_DAILY_REPORT:-2}"
export AI_MAX_FALLBACKS_EVOLUTION="${AI_MAX_FALLBACKS_EVOLUTION:-2}"
export AI_MAX_FALLBACKS_INCUBATOR="${AI_MAX_FALLBACKS_INCUBATOR:-2}"
export AI_MAX_FALLBACKS_WATCHDOG="${AI_MAX_FALLBACKS_WATCHDOG:-2}"
export AI_MODEL_RANK_FILE="${AI_MODEL_RANK_FILE:-${PROJECT_DIR}/ai_model_rank.json}"

timestamp() {
  date -Is
}

echo "[$(timestamp)] ${JOB_NAME}: start timeout=${JOB_TIMEOUT_SECONDS}s script=${SCRIPT_PATH}"

if /usr/bin/flock -E 99 -n "$LOCK_FILE" \
  /usr/bin/timeout -k "${KILL_AFTER_SECONDS}s" "${JOB_TIMEOUT_SECONDS}s" \
  "$INFISICAL_BIN" --env "$INFISICAL_ENV" --projectId "$INFISICAL_PROJECT_ID" -- \
  "$PYTHON_BIN" "$SCRIPT_PATH" "$@"; then
  echo "[$(timestamp)] ${JOB_NAME}: success"
else
  status=$?
  if [ "$status" -eq 99 ]; then
    echo "[$(timestamp)] ${JOB_NAME}: skipped, previous run still active"
    exit 0
  fi
  if [ "$status" -eq 124 ] || [ "$status" -eq 137 ]; then
    echo "[$(timestamp)] ${JOB_NAME}: timed out after ${JOB_TIMEOUT_SECONDS}s" >&2
  else
    echo "[$(timestamp)] ${JOB_NAME}: failed with exit code ${status}" >&2
  fi
  exit "$status"
fi
