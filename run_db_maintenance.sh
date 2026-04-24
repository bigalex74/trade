#!/usr/bin/env bash
set -euo pipefail

USER_HOME="${HOME:-/home/user}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${PROJECT_DIR}/db_maintenance.sql"

timestamp() {
  date -Is
}

echo "[$(timestamp)] Starting Deep DB Maintenance (Sunday Cycle)..."

# Выполняем SQL через docker exec
if docker exec n8n-docker-db-1 psql -U n8n_user -d market_research -f "/home/user/trade/db_maintenance.sql"; then
  echo "[$(timestamp)] DB Maintenance SUCCESS."
else
  echo "[$(timestamp)] DB Maintenance FAILED." >&2
  exit 1
fi
