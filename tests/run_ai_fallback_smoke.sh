#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"

echo "[1/2] Python compile"
"$PYTHON_BIN" -m py_compile gemini_cli_runner.py ai_cost_guard.py ai_paper_trader.py tests/fake_gemini_cli.py

echo "[2/2] Timeout fallback continues to next model"
AI_COST_GUARD_ENABLED=0 \
GEMINI_BIN="$PROJECT_DIR/tests/fake_gemini_cli.py" \
GEMINI_TIMEOUT_SECONDS=6 \
GEMINI_ATTEMPT_TIMEOUT_SECONDS_TRADER=1 \
FAKE_GEMINI_TIMEOUT_MODELS=gemini-timeout \
FAKE_GEMINI_TIMEOUT_SLEEP=3 \
"$PYTHON_BIN" - <<'PY'
from gemini_cli_runner import call_ai_json_with_fallback

data, model = call_ai_json_with_fallback(
    "Respond ONLY raw JSON object with keys: summary, actions.",
    models=["gemini-timeout", "gemini-ok"],
    name="fallback_smoke",
    category="trader",
)
print({"model": model, "data": data})
if model != "gemini-ok":
    raise SystemExit(f"expected fallback to gemini-ok, got {model}")
if not isinstance(data, dict):
    raise SystemExit("expected JSON dict")
PY

echo "AI fallback smoke tests passed"
