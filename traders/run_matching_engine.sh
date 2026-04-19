#!/bin/bash
# Воркер для Биржевого Ядра (Matching Engine)

LOG_FILE="/home/user/logs/traders/matching_engine.log"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/order_matching_engine.py"
ENV_FILE="/home/user/.env.trading"

# Загрузка секретов
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Matching Engine worker started." >> "$LOG_FILE"

while true; do
    NOW_HOUR=$(date +%H)
    NOW_MIN=$(date +%M)
    DOW=$(date +%u)

    IS_OPEN=0
    if [ "$DEBUG_MODE" = "true" ]; then
        IS_OPEN=1
    elif [ "$DOW" -le 5 ]; then
        if [ "$NOW_HOUR" -ge 10 ]; then
            if [ "$NOW_HOUR" -lt 23 ] || ([ "$NOW_HOUR" -eq 23 ] && [ "$NOW_MIN" -lt 50 ]); then
                IS_OPEN=1
            fi
        fi
    fi

    if [ "$IS_OPEN" -eq 1 ]; then
        # Исполнение заявок (каждую минуту)
        timeout 60 $PYTHON_BIN $SCRIPT >> "$LOG_FILE" 2>&1
        sleep 60
    else
        sleep 60
    fi
done
