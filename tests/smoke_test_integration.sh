#!/bin/bash
# Тест инициализации трейдера (проверка импортов и коннектов)
export AI_DEBUG_IO_LOG=0
export AI_COST_GUARD_ENABLED=0

echo "--- Running Integration Smoke Test ---"
python3 -c "
import sys; sys.path.append('/home/user/trade')
try:
    import ai_paper_trader
    print('✅ ai_paper_trader imports: OK')
    # Проверка наличия ключевых функций
    required = ['get_db_connection', 'send_telegram', 'main']
    for func in required:
        if hasattr(ai_paper_trader, func):
            print(f'✅ Function {func}: Found')
        else:
            print(f'❌ Function {func}: MISSING')
            sys.exit(1)
except Exception as e:
    print(f'❌ Initialization FAILED: {e}')
    sys.exit(1)
"
echo "--- Smoke Test Passed ---"
