#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export POSTMARKET_AI_TIMEOUT_SECONDS="${POSTMARKET_AI_TIMEOUT_SECONDS:-900}"
exec "${PROJECT_DIR}/run_postmarket_ai_job.sh" ai_watchdog_analyzer "${PROJECT_DIR}/ai_watchdog_analyzer.py" "$@"
