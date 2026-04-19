#!/bin/bash
# Изолированный воркер для крипты: Passive_Palych

LOG_FILE="/home/user/logs/traders/crypto_Passive_Palych.log"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/ai_crypto_trader.py"

# Загрузка общих секретов из файла
if [ -f "/home/user/.env.trading" ]; then
    set -a
    source "/home/user/.env.trading"
    set +a
fi

while true; do
    echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Tick: Passive_Palych (Crypto)" >> "$LOG_FILE"
    
    # Вызов трейдера с таймаутом (рынок крипты открыт всегда)
    timeout 300 $PYTHON_BIN $SCRIPT "Passive_Palych" >> "$LOG_FILE" 2>&1
    
    # ШТАТНЫЙ ЦИКЛ: 5 минут
    sleep 300
done
