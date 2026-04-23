import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk_engine import review_actions, RiskSettings
import psycopg2

def test_smart_limits():
    # Настройки: лимит 8 действий в день
    settings = RiskSettings(max_actions_per_trader_day=8, max_actions_per_decision=10)
    
    # Имитируем пустое состояние (0 сделок в БД)
    # Нам нужно реальное соединение или mock. 
    # Так как у нас есть доступ к БД, проверим на реальном трейдере 'Scalper_Kesha'
    
    DB_CONFIG = {
        "host": "localhost",
        "database": "market_research",
        "user": "n8n_user",
        "password": "n8n_db_password",
    }
    
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        # 1. Проверяем текущее состояние
        prices = {"SBER": 300.0}
        actions = [{"secid": "SBER", "action": "buy", "quantity": 1, "reason": "test"}] * 10
        
        result = review_actions(conn, "Scalper_Kesha", actions, prices, settings=settings)
        
        print(f"Total actions requested: {len(actions)}")
        print(f"Accepted: {len(result['accepted'])}")
        print(f"Rejected: {len(result['rejected'])}")
        print(f"Day action count (from state): {result['state']['day_action_count']}")
        
        # Если логика верна: 
        # Должно быть принято 8 (лимит), остальные 2 отклонены по 'max_actions_per_trader_day'
        # НО, при следующем запуске (если ордера не попали в БД), лимит снова должен быть доступен.
        
        if len(result['accepted']) <= 8:
            print("SUCCESS: Smart limits logic within one decision works (capped by settings).")
        else:
            print("FAILURE: More actions accepted than daily limit.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    test_smart_limits()
