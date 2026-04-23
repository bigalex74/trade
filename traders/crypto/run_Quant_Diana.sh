#!/bin/bash
set -u
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRADER="$(basename "$0" .sh | sed 's/^run_//')"
exec "${PROJECT_DIR}/run_ai_crypto_trader_once.sh" "$TRADER" >> "/home/user/logs/traders/crypto_$TRADER.log" 2>&1
