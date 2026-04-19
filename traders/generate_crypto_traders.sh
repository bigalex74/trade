#!/bin/bash
# ГЕНЕРАТОР ВОРКЕРОВ ДЛЯ КРИПТЫ (Crypto Division)

TRADERS=(
    "VSA_Victor" "Chaos_Bill" "Elliott_Alex" "Contrarian_Ricardo" 
    "Quant_Diana" "PriceAction_Nikita" "Passive_Palych" 
    "Scalper_Kesha" "Value_Monya" "Index_Tracker" "Meta_Oracle"
)

TEMPLATE_DIR="/home/user/traders/crypto"
ENV_FILE="/home/user/.env.trading"

mkdir -p "$TEMPLATE_DIR"

for TRADER in "${TRADERS[@]}"; do
    FILE="$TEMPLATE_DIR/run_$TRADER.sh"
    cat <<EOF > "$FILE"
#!/bin/bash
# Изолированный воркер для крипты: $TRADER

LOG_FILE="/home/user/logs/traders/crypto_$TRADER.log"
PYTHON_BIN="/home/user/trading_venv/bin/python"
SCRIPT="/home/user/ai_crypto_trader.py"

# Загрузка общих секретов из файла
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

while true; do
    echo "[ \$(date '+%Y-%m-%d %H:%M:%S') ] Tick: $TRADER (Crypto)" >> "\$LOG_FILE"
    
    # Вызов трейдера с таймаутом (рынок крипты открыт всегда)
    timeout 300 \$PYTHON_BIN \$SCRIPT "$TRADER" >> "\$LOG_FILE" 2>&1
    
    # ШТАТНЫЙ ЦИКЛ: 5 минут
    sleep 300
done
EOF
    chmod +x "$FILE"
done
echo "Regenerated Crypto worker scripts with 5-min cycle (24/7)."
