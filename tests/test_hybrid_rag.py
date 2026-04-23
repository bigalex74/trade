import sys
import os
import unittest
import time
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hybrid_rag

class TestHybridRag(unittest.TestCase):
    def test_candidate_query_text(self):
        text = hybrid_rag._candidate_query_text(
            "TestTrader", "TestStrategy", {"SBER": {"p": 300}}, 
            [{"secid": "GAZP"}], ["hist1"], "YELLOW"
        )
        self.assertIn("TestTrader", text)
        self.assertIn("YELLOW", text)

    def test_embedding_cache_logic(self):
        client = hybrid_rag.EmbeddingClient(provider="hash")
        text = "Exact string for caching test."
        cache_path = client._get_cache_path(hybrid_rag._truncate(text, hybrid_rag.MAX_EMBED_TEXT_CHARS))
        
        if os.path.exists(cache_path):
            os.remove(cache_path)
            
        # 1. Холодный старт (создаем кеш)
        v1 = client.embed(text)
        self.assertTrue(os.path.exists(cache_path), f"Cache file not created at {cache_path}")
        
        # 2. Горячий старт (должен взять из файла)
        # Подменяем методы, которые вызывают реальный эмбеддинг
        with patch.object(client, '_hash_embedding', return_value=[0.1, 0.2]) as mock_hash,              patch.object(client, '_ollama_embedding', return_value=[0.1, 0.2]) as mock_ollama:
            v2 = client.embed(text)
            mock_hash.assert_not_called()
            mock_ollama.assert_not_called()
            self.assertEqual(v1, v2)

    def test_format_news_hit(self):
        hit = {
            "payload": {
                "secids": ["SBER", "VTBR"],
                "title": "Bank news",
                "published_at": "2026-04-23"
            }
        }
        formatted = hybrid_rag._format_news_hit(hit)
        self.assertIn("SBER,VTBR", formatted)
        self.assertIn("Bank news", formatted)

if __name__ == "__main__":
    unittest.main()
