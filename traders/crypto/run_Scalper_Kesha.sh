#!/bin/bash
set -u
TRADER="$(basename "$0" .sh | sed 's/^run_//')"
exec /home/user/run_ai_crypto_trader_once.sh "$TRADER" >> "/home/user/logs/traders/crypto_$TRADER.log" 2>&1
