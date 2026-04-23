#!/bin/bash
set -u

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOCK_FILE="/tmp/ai_crypto_traders_dispatcher.lock"
LOG_DIR="/home/user/logs/traders"
RUNNER="${PROJECT_DIR}/run_ai_crypto_trader_once.sh"
INTERVAL_SECONDS="${AI_CRYPTO_TRADER_STAGGER_SECONDS:-25}"

TRADERS=(
  "Chaos_Bill"
  "Contrarian_Ricardo"
  "Elliott_Alex"
  "Index_Tracker"
  "Meta_Oracle"
  "Passive_Palych"
  "PriceAction_Nikita"
  "Quant_Diana"
  "Scalper_Kesha"
  "VSA_Victor"
  "Value_Monya"
)

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Previous crypto trader dispatch is still running; skipping."
  exit 0
fi

echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Crypto trader cron dispatch started."

for index in "${!TRADERS[@]}"; do
  trader="${TRADERS[$index]}"
  delay=$((index * INTERVAL_SECONDS))
  (
    sleep "$delay"
    "$RUNNER" "$trader" >> "$LOG_DIR/crypto_$trader.log" 2>&1
  ) &
done

wait
echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] Crypto trader cron dispatch finished."
