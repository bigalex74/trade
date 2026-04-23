#!/bin/bash
set -e
PROJECT_DIR="/home/user/trade"
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

echo "========================================"
echo "🚀 ЗАПУСК ВСЕХ ТЕСТОВ ТОРГОВОЙ СИСТЕМЫ"
echo "========================================"

echo -e "\n1. [INTEGRATION] Smoke Test (Initialization & Imports)..."
/home/user/trade/tests/smoke_test_integration.sh

echo -e "\n2. [UNIT] Risk Engine (Smart Limits)..."
python3 /home/user/trade/tests/test_risk_smart_limits.py

echo -e "\n3. [UNIT] RAG Caching (Embedding speed)..."
python3 /home/user/trade/tests/test_rag_cache.py

echo -e "\n4. [SYNTAX] All Python files..."
find /home/user/trade -name "*.py" -exec python3 -m py_compile {} +

echo -e "\n========================================"
echo "✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО"
echo "========================================"
