#!/usr/bin/env bash
set -euo pipefail

export POSTMARKET_AI_TIMEOUT_SECONDS="${POSTMARKET_AI_TIMEOUT_SECONDS:-900}"
exec /home/user/run_postmarket_ai_job.sh ai_evolution /home/user/ai_evolution.py "$@"
