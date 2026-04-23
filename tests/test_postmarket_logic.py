import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_genetic_incubator
import ai_evolution

class TestPostmarketLogic(unittest.TestCase):
    def test_compact_indicators_incubator(self):
        # Тест фильтрации индикаторов в инкубаторе
        raw = {"RSI": 70.5, "UNKNOWN": 1.2, "MACD_line": 0.5, "SMA_50": 300.0}
        compacted = ai_genetic_incubator.compact_indicators(raw)
        self.assertIn("RSI", compacted)
        self.assertIn("MACD_line", compacted)
        self.assertIn("SMA_50", compacted)
        self.assertNotIn("UNKNOWN", compacted)
        self.assertEqual(compacted["RSI"], 70.5)

    def test_compact_indicators_evolution(self):
        # Аналогичный тест для эволюции (логика должна быть идентичной)
        raw = {"ATR": 5.5, "OTHER": 0.1, "fractal_up": True}
        compacted = ai_evolution.compact_indicators(raw)
        self.assertIn("ATR", compacted)
        self.assertIn("fractal_up", compacted)
        self.assertNotIn("OTHER", compacted)

    def test_imports_incubator(self):
        # Проверка базовой инициализации
        self.assertTrue(callable(ai_genetic_incubator.synthesize_strategies))
        self.assertTrue(callable(ai_genetic_incubator.get_db_connection))

    def test_imports_evolution(self):
        self.assertTrue(callable(ai_evolution.deep_analyze_and_evolve))
        self.assertTrue(callable(ai_evolution.get_db_connection))

if __name__ == "__main__":
    unittest.main()
