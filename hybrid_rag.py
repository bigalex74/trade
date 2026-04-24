import hashlib
import json
import math
import os
import re
import uuid
import time
import requests
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2

# CONFIG
EMBEDDING_PROVIDER = os.getenv("AI_RAG_EMBEDDING_PROVIDER", "ollama")
EMBEDDING_MODEL = os.getenv("AI_RAG_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_URL = os.getenv("AI_RAG_OLLAMA_URL", "http://localhost:11434/api/embeddings")
QDRANT_URL = os.getenv("AI_RAG_QDRANT_URL", "http://localhost:6333")
API_KEY_QDRANT = os.getenv("AI_RAG_QDRANT_API_KEY", "")

MAX_EMBED_TEXT_CHARS = 1024
HASH_VECTOR_SIZE = 768

def _truncate(text: str, limit: int) -> str:
    return (text or "")[:limit]

class EmbeddingClient:
    def __init__(self, provider: str = EMBEDDING_PROVIDER):
        self.provider = provider
        self.cache_dir = "/tmp/trading_cache/embeddings"
        self.cache_ttl_seconds = 600

    def _get_cache_path(self, text: str) -> str:
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{self.provider}_{text_hash}.json")

    def _load_from_cache(self, cache_path: str) -> list[float] | None:
        if not os.path.exists(cache_path): return None
        try:
            if time.time() - os.path.getmtime(cache_path) > self.cache_ttl_seconds: return None
            with open(cache_path, "r") as f: return json.load(f)
        except: return None

    def _save_to_cache(self, cache_path: str, vector: list[float]) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(cache_path, "w") as f: json.dump(vector, f)
        except: pass

    def embed(self, text: str) -> list[float]:
        clean_text = _truncate(text, MAX_EMBED_TEXT_CHARS)
        cache_path = self._get_cache_path(clean_text)
        cached = self._load_from_cache(cache_path)
        if cached: return cached

        if self.provider == "hash": vector = self._hash_embedding(clean_text)
        else: vector = self._ollama_embedding(clean_text)
        
        self._save_to_cache(cache_path, vector)
        return vector

    def _ollama_embedding(self, text: str) -> list[float]:
        try:
            resp = requests.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "prompt": text}, timeout=10)
            return resp.json().get("embedding", [0.0] * HASH_VECTOR_SIZE)
        except: return [0.0] * HASH_VECTOR_SIZE

    def _hash_embedding(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        vector = []
        for i in range(HASH_VECTOR_SIZE):
            idx = i % len(h)
            vector.append(float(h[idx]) / 255.0)
        return vector

def _search_collection(collection: str, vector: list[float], limit: int = 3) -> list[dict[str, Any]]:
    try:
        url = f"{QDRANT_URL}/collections/{collection}/points/search"
        payload = {"vector": vector, "limit": limit, "with_payload": True}
        resp = requests.post(url, json=payload, headers={"api-key": API_KEY_QDRANT}, timeout=10)
        if resp.status_code == 200: return resp.json().get("result", [])
    except: pass
    return []

def _format_news_hit(hit: dict[str, Any]) -> str:
    p = hit.get("payload", {})
    return f"[{p.get('published_at', 'N/A')}] {','.join(p.get('secids', []))}: {p.get('title', 'No Title')}"

def _candidate_query_text(trader_name, strategy, market_features, positions, recent_history, market_regime):
    return f"Trader: {trader_name}. Strategy: {strategy}. Regime: {market_regime}. Positions: {positions}. History: {recent_history}"

def build_trader_rag_context(trader_name, strategy, market_features, positions, recent_history=None, market_regime=None, log_func=None):
    if os.getenv("AI_RAG_ENABLED", "1") == "0": return ""
    try:
        embedder = EmbeddingClient()
        vector = embedder.embed(_candidate_query_text(trader_name, strategy, market_features, positions, recent_history, market_regime))
        
        # Поиск уроков успеха (Alpha Memory), сетапов и новостей
        alpha_hits = _search_collection("alpha_memory", vector, limit=2)
        setups_hits = _search_collection("trading_setups", vector, limit=2)
        news_hits = _search_collection("market_news", vector, limit=3)
        
        parts = []
        if alpha_hits:
            parts.append("### 🏆 HISTORICAL SUCCESS CASES (Few-Shot):")
            for h in alpha_hits: parts.append(h.get("payload", {}).get("text", ""))
        if setups_hits:
            parts.append("### 🔍 RELEVANT STRATEGY SETUPS:")
            for h in setups_hits: parts.append(h.get("payload", {}).get("text", ""))
        if news_hits:
            parts.append("### 📰 RELEVANT MARKET NEWS:")
            for h in news_hits: parts.append(_format_news_hit(h))
            
        context = "\n\n".join(parts)
        if log_func: log_func(f"[{trader_name}] Hybrid RAG: alpha={len(alpha_hits)} setups={len(setups_hits)} news={len(news_hits)} chars={len(context)}")
        return context
    except: return ""
