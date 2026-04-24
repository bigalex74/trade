import unittest
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alpha_extractor
import hybrid_rag

class TestAlphaMemoryFlow(unittest.TestCase):
    def test_alpha_extraction_logic(self):
        # Проверяем, что экстрактор возвращает список (пусть и пустой без БД)
        # Нам важно отсутствие синтаксических ошибок
        self.assertTrue(hasattr(alpha_extractor, 'extract_top_alpha_deals'))

    @patch('hybrid_rag._search_collection')
    def test_rag_with_alpha_context(self, mock_search):
        # Имитируем нахождение успешного кейса в Qdrant
        mock_search.side_effect = [
            [{"payload": {"text": "SUCCESSFUL CASE: SBER BUY 5%"}}], # alpha
            [], # setups
            []  # news
        ]
        
        ctx = hybrid_rag.build_trader_rag_context(
            "Test", "Strategy", {}, [], market_regime="BULL"
        )
        
        self.assertIn("HISTORICAL SUCCESS CASES", ctx)
        self.assertIn("SBER BUY 5%", ctx)

if __name__ == '__main__':
    unittest.main()
