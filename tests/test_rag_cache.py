import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_rag import EmbeddingClient

def test_cache():
    # Очищаем кеш перед тестом
    cache_dir = "/tmp/trading_cache/embeddings"
    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir)
        
    client = EmbeddingClient(provider="hash") # 'hash' работает локально без внешних API
    text = "Тестовый рыночный контекст для проверки кеширования эмбеддингов."
    
    # 1. Первый вызов (холодный)
    start = time.time()
    v1 = client.embed(text)
    cold_duration = time.time() - start
    print(f"Cold duration: {cold_duration:.4f}s")
    
    # 2. Второй вызов (горячий)
    start = time.time()
    v2 = client.embed(text)
    hot_duration = time.time() - start
    print(f"Hot duration: {hot_duration:.4f}s")
    
    if v1 == v2 and hot_duration < cold_duration:
        print("SUCCESS: Caching works!")
    else:
        print("FAILURE: Caching issue.")

if __name__ == "__main__":
    test_cache()
