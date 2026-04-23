#!/bin/bash
set -e
PROJECT_DIR="/home/user/trade"
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

echo "========================================"
echo "🚀 ЗАПУСК ПОЛНОГО НАБОРА ТЕСТОВ (v0.5.0)"
echo "========================================"

echo -e "\n1. [INTEGRATION] Smoke Test (Initialization)..."
/home/user/trade/tests/smoke_test_integration.sh

echo -e "\n2. [UNIT] AI Runner (Parsing & Fallback)..."
python3 /home/user/trade/tests/test_ai_runner.py

echo -e "\n3. [UNIT] Hybrid RAG (Cache & Context)..."
python3 /home/user/trade/tests/test_hybrid_rag.py

echo -e "\n4. [UNIT] Risk Engine (Rules & Safety)..."
python3 /home/user/trade/tests/test_risk_engine_full.py

echo -e "\n5. [UNIT] Smart Limits (Journal/Orders logic)..."
python3 /home/user/trade/tests/test_risk_smart_limits.py

echo -e "\n6. [SYNTAX] All Python files..."
find /home/user/trade -name "*.py" -maxdepth 2 -exec python3 -m py_compile {} +

echo -e "\n========================================"
echo "✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ: СИСТЕМА СТАБИЛЬНА"
echo "========================================"
