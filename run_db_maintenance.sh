#!/usr/bin/env bash
set -euo pipefail

USER_HOME="${HOME:-/home/user}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${PROJECT_DIR}/db_maintenance.sql"

if [ -f "${USER_HOME}/.env.trading" ]; then
  set -a
  source "${USER_HOME}/.env.trading"
  set +a
fi

TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="923741104"
PROXY="http://127.0.0.1:10808"

timestamp() {
  date -Is
}

send_telegram() {
  local msg="$1"
  if [ -n "$TELEGRAM_TOKEN" ]; then
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
      -x "$PROXY" \
      -d "chat_id=${TELEGRAM_CHAT_ID}" \
      -d "parse_mode=HTML" \
      -d "text=${msg}" > /dev/null
  fi
}

echo "[$(timestamp)] Starting Deep DB Maintenance (Sunday Cycle)..."

# Выполняем SQL через docker exec
if docker exec n8n-docker-db-1 psql -U n8n_user -d market_research -f "/home/user/trade/db_maintenance.sql"; then
  MSG="🧹 <b>DB MAINTENANCE SUCCESS</b>
━━━━━━━━━━━━━━━━━━
✅ <b>ЧТО СДЕЛАНО:</b>
Выполнена глубокая оптимизация PostgreSQL.
• <u>REINDEX</u>: Пересобраны индексы journal, orders, logs.
• <u>VACUUM FULL</u>: Таблицы переупакованы, место освобождено.
• <u>ANALYZE</u>: Статистика планировщика обновлена."
  send_telegram "$MSG"
  echo "[$(timestamp)] DB Maintenance SUCCESS."
else
  MSG="❌ <b>DB MAINTENANCE FAILED</b>
━━━━━━━━━━━━━━━━━━
Произошла ошибка при выполнении воскресного цикла обслуживания базы данных. Проверьте логи: logs/db_maintenance.log"
  send_telegram "$MSG"
  echo "[$(timestamp)] DB Maintenance FAILED." >&2
  exit 1
fi
