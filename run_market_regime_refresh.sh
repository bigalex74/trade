#!/usr/bin/env bash
set -euo pipefail

cd /home/user
exec /home/user/run_infisical_quiet.sh /home/user/trading_venv/bin/python /home/user/market_regime.py "$@"
