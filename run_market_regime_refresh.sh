#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
cd "$PROJECT_DIR"
exec "${PROJECT_DIR}/run_infisical_quiet.sh" "$PYTHON_BIN" "${PROJECT_DIR}/market_regime.py" "$@"
