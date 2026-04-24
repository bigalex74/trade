import unittest
import sys
import os
import psycopg2
from datetime import datetime, timezone, timedelta
from contextlib import closing

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_cost_guard

class TestAdaptiveGuard(unittest.TestCase):
    def setUp(self):
        self.model = "test-adaptive-model"
        self.cat = "test-cat"
        # Очищаем перед тестом
        with closing(ai_cost_guard.connect()) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trading.ai_model_cooldown WHERE model_id = %s", (self.model,))
            conn.commit()

    def test_exponential_backoff(self):
        # 1. Первый сбой (должен быть уровень 1)
        ai_cost_guard.log_call(self.cat, "test", None, self.model, "", "", 1, "error", error="429: limit")
        
        with closing(ai_cost_guard.connect()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT backoff_level, unavailable_until FROM trading.ai_model_cooldown WHERE model_id = %s", (self.model,))
                lvl, until = cur.fetchone()
                self.assertEqual(lvl, 1)
                
        # 2. Второй сбой (уровень должен стать 2)
        ai_cost_guard.log_call(self.cat, "test", None, self.model, "", "", 1, "error", error="429: limit")
        
        with closing(ai_cost_guard.connect()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT backoff_level FROM trading.ai_model_cooldown WHERE model_id = %s", (self.model,))
                lvl = cur.fetchone()[0]
                self.assertEqual(lvl, 2)

    def test_success_reset(self):
        # Серия сбоев
        ai_cost_guard.log_call(self.cat, "test", None, self.model, "", "", 1, "error", error="429")
        ai_cost_guard.log_call(self.cat, "test", None, self.model, "", "", 1, "error", error="429")
        
        # Успех (должен снизить уровень)
        ai_cost_guard.log_call(self.cat, "test", None, self.model, "", "", 1, "success")
        
        with closing(ai_cost_guard.connect()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT backoff_level FROM trading.ai_model_cooldown WHERE model_id = %s", (self.model,))
                lvl = cur.fetchone()[0]
                self.assertEqual(lvl, 1) # С 2 упал до 1

if __name__ == '__main__':
    unittest.main()
