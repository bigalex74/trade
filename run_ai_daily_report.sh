#!/usr/bin/env bash
set -euo pipefail

export POSTMARKET_AI_TIMEOUT_SECONDS="${POSTMARKET_AI_TIMEOUT_SECONDS:-2400}"
exec /home/user/run_postmarket_ai_job.sh ai_daily_report /home/user/ai_daily_report.py "$@"
