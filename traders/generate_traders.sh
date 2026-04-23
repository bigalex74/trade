#!/bin/bash
# ГЕНЕРАТОР ВОРКЕРОВ (v2.3 - Production Edition)

TRADERS=(
    "VSA_Victor" "Chaos_Bill" "Elliott_Alex" "Contrarian_Ricardo" 
    "Quant_Diana" "PriceAction_Nikita" "Passive_Palych" 
    "Scalper_Kesha" "Value_Monya" "Index_Tracker" "Meta_Oracle"
)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="${PROJECT_DIR}/traders"
ENV_FILE="/home/user/.env.trading"

for TRADER in "${TRADERS[@]}"; do
    FILE="$TEMPLATE_DIR/run_$TRADER.sh"
    cat <<EOF > "$FILE"
#!/bin/bash
# Изолированный воркер для $TRADER

LOG_FILE="/home/user/logs/traders/$TRADER.log"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="${PROJECT_DIR}/ai_paper_trader.py"

# 1. Загрузка общих секретов из файла
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

while true; do
    # Проверка: Пн-Пт, 10:00 - 23:50 ИЛИ DEBUG_MODE
    IS_OPEN=0
    if [ "\$DEBUG_MODE" = "true" ]; then
        IS_OPEN=1
    else
        DOW=\$(date +%u)
        NOW_HOUR=\$(date +%H)
        NOW_MIN=\$(date +%M)
        if [ "\$DOW" -le 5 ] && [ "\$NOW_HOUR" -ge 10 ]; then
            if [ "\$NOW_HOUR" -lt 23 ] || ([ "\$NOW_HOUR" -eq 23 ] && [ "\$NOW_MIN" -lt 50 ]); then
                IS_OPEN=1
            fi
        fi
    fi

    if [ "\$IS_OPEN" -eq 1 ]; then
        echo "[ \$(date '+%Y-%m-%d %H:%M:%S') ] Tick: $TRADER" >> "\$LOG_FILE"
        # Вызов трейдера с таймаутом
        timeout 300 \$PYTHON_BIN \$SCRIPT "$TRADER" >> "\$LOG_FILE" 2>&1
        
        # ШТАТНЫЙ ЦИКЛ: 5 минут (300 секунд)
        sleep 300
    else
        # Рынок закрыт - проверка раз в минуту
        sleep 60
    fi
done
EOF
    chmod +x "$FILE"
done
echo "Regenerated 10 worker scripts with 5-min cycle."
