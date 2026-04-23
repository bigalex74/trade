#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
BACKUP_ROOT="${PROJECT_BACKUP_ROOT:-/home/user/project_backup/scoped_archives}"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
ARCHIVE_PATH="$BACKUP_ROOT/trading_ops_$TIMESTAMP.tar.gz"

INCLUDE_PATHS=(
  "docs"
  "ai_model_rank.json"
  "algo_kb_client.py"
  "algo_kb_market_summary.py"
  "gemini_cli_runner.py"
  "market_research_context.py"
  "market_research_maintenance.py"
  "market_research_market_pipeline.py"
  "trading_core_market_pipeline.py"
  "ai_evolution.py"
  "ai_genetic_incubator.py"
  "ai_watchdog_analyzer.py"
  "ai_daily_report.py"
  "ai_sentiment_oracle.py"
  "ai_job_store.py"
  "ai_job_dispatcher.py"
  "ai_job_worker.py"
  "ai_paper_trader.py"
  "run_postmarket_ai_job.sh"
  "run_ai_evolution.sh"
  "run_ai_genetic_incubator.sh"
  "run_ai_watchdog_analyzer.sh"
  "run_ai_daily_report.sh"
  "run_ai_job_dispatcher.sh"
  "run_ai_trader_once.sh"
  "run_algo_kb_market_summary.sh"
  "run_infisical_quiet.sh"
  "run_logrotate_trading.sh"
  "run_market_research_cleanup_intraday.sh"
  "run_market_research_collect_1d.sh"
  "run_market_research_collect_1h.sh"
  "run_market_research_collect_1m.sh"
  "run_market_research_healthcheck.sh"
  "run_market_research_refresh_daily.sh"
  "run_market_research_refresh_intraday.sh"
  "run_matching_engine_once.sh"
  "logrotate-trading.conf"
)

mkdir -p "$BACKUP_ROOT"
cd "$BASE_DIR"

existing_paths=()
for path in "${INCLUDE_PATHS[@]}"; do
  if [ -e "$path" ]; then
    existing_paths+=("$path")
  else
    echo "[$(date -Is)] backup_project: skip missing path $path"
  fi
done

if [ "${#existing_paths[@]}" -eq 0 ]; then
  echo "[$(date -Is)] backup_project: no files to archive" >&2
  exit 1
fi

tar \
  --exclude='*.log' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.mypy_cache' \
  -czf "$ARCHIVE_PATH" \
  "${existing_paths[@]}"

find "$BACKUP_ROOT" -type f -name 'trading_ops_*.tar.gz' -mtime +14 -delete

echo "[$(date -Is)] scoped project backup completed: $ARCHIVE_PATH"
