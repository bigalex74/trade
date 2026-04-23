#!/usr/bin/env bash
set -euo pipefail

export POSTMARKET_AI_TIMEOUT_SECONDS="${POSTMARKET_AI_TIMEOUT_SECONDS:-900}"
exec /home/user/run_postmarket_ai_job.sh ai_genetic_incubator /home/user/ai_genetic_incubator.py "$@"
