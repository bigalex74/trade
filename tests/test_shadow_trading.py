import sys
import os
import unittest
import psycopg2
from decimal import Decimal
from contextlib import closing

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_paper_trader

class TestShadowTrading(unittest.TestCase):
    def setUp(self):
        self.db_config = {
            "host": "localhost",
            "database": "market_research",
            "user": "n8n_user",
            "password": "n8n_db_password",
        }
        # Очищаем тень перед тестом
        with closing(psycopg2.connect(**self.db_config)) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trading.shadow_orders WHERE trader_name = 'Test_Shadow_Trader'")
                cur.execute("DELETE FROM trading.shadow_portfolio WHERE trader_name = 'Test_Shadow_Trader'")
            conn.commit()

    def test_shadow_initialization_and_order(self):
        # Имитируем запуск через CLI с флагом --shadow
        os.environ["AI_TEST_MODE"] = "1"
        trader_name = "Scalper_Kesha" # Используем существующего трейдера для конфига
        
        # 1. Проверяем функцию execute_trade_actions в режиме тени
        actions = [{"secid": "SBER", "action": "buy", "quantity": 1, "target_price": 300.0, "reason": "shadow test"}]
        snapshots = {"SBER": {"price": Decimal("300.0")}}
        
        review = ai_paper_trader.execute_trade_actions(
            trader_name, actions, Decimal("10000.0"), snapshots, "test-model", use_shadow=True
        )
        
        self.assertIsNotNone(review)
        self.assertEqual(len(review["accepted"]), 1)
        
        # 2. Проверяем что ордер попал в ТЕНЕВУЮ таблицу
        with closing(psycopg2.connect(**self.db_config)) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM trading.shadow_orders WHERE trader_name = %s", (trader_name,))
                shadow_count = cur.fetchone()[0]
                
                cur.execute("SELECT count(*) FROM trading.orders WHERE trader_name = %s AND reason = 'shadow test'", (trader_name,))
                real_count = cur.fetchone()[0]
                
        self.assertGreater(shadow_count, 0, "Order should be in shadow_orders")
        self.assertEqual(real_count, 0, "Order should NOT be in real orders table")

if __name__ == "__main__":
    unittest.main()
