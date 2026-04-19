#!/bin/bash
# Воркер для часового отчета CRYPTO

LOG_FILE="/home/user/logs/traders/crypto_hourly_report.log"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/ai_crypto_hourly_report.py"
ENV_FILE="/home/user/.env.trading"

# Загрузка секретов
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Crypto Hourly report worker started." >> "$LOG_FILE"

while true; do
    NOW_MIN=$(date +%M)
    # Крипто отчет в 30 минут каждого часа (24/7)
    if [ "$NOW_MIN" -eq 30 ]; then
        echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Generating crypto summary report..." >> "$LOG_FILE"
        $PYTHON_BIN $SCRIPT >> "$LOG_FILE" 2>&1
        sleep 120
    fi
    sleep 30
done
