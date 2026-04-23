#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

from market_regime import compact_regime, latest_market_regime
from market_research_context import load_market_context


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

QDRANT_URL = os.getenv("AI_RAG_QDRANT_URL", "http://localhost:6333").rstrip("/")
QDRANT_TIMEOUT = float(os.getenv("AI_RAG_QDRANT_TIMEOUT_SECONDS", "10"))
TRADE_SETUPS_COLLECTION = os.getenv("AI_RAG_SETUPS_COLLECTION", "trade_setups_memory_v1")
MARKET_NEWS_COLLECTION = os.getenv("AI_RAG_NEWS_COLLECTION", "market_news_memory_v1")
MARKET_SNAPSHOTS_COLLECTION = os.getenv("AI_RAG_MARKET_COLLECTION", "market_snapshots_memory_v1")
EMBEDDING_PROVIDER = os.getenv("AI_RAG_EMBEDDING_PROVIDER", "ollama").lower()
OLLAMA_URL = os.getenv("AI_RAG_OLLAMA_URL", "http://localhost:11434/api/embeddings")
EMBEDDING_MODEL = os.getenv("AI_RAG_EMBEDDING_MODEL", "nomic-embed-text")
HASH_VECTOR_SIZE = int(os.getenv("AI_RAG_HASH_VECTOR_SIZE", "768"))
MAX_EMBED_TEXT_CHARS = int(os.getenv("AI_RAG_EMBED_TEXT_MAX_CHARS", "6000"))
MAX_RAG_CONTEXT_CHARS = int(os.getenv("AI_RAG_MAX_CHARS", "700"))
RAG_NAMESPACE = uuid.UUID("b82a89cf-5661-4a4f-9c61-c076e5e78e7b")
MAX_NEWS_INFERRED_SECIDS = int(os.getenv("AI_RAG_NEWS_MAX_INFERRED_SECIDS", "4"))

GENERIC_NEWS_TERMS = {
    "акции",
    "биржа",
    "банк",
    "компания",
    "рынок",
    "россия",
    "московская биржа",
    "moscow exchange",
}


def _json_default(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def stable_point_id(source_key: str) -> str:
    return str(uuid.uuid5(RAG_NAMESPACE, source_key))


def source_hash(text: str, payload: dict[str, Any] | None = None) -> str:
    raw = json.dumps(
        {
            "text": text,
            "payload": payload or {},
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model": EMBEDDING_MODEL,
            "hash_vector_size": HASH_VECTOR_SIZE if EMBEDDING_PROVIDER == "hash" else None,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _number(value: Any):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _round(value: Any, digits: int = 3):
    number = _number(value)
    if number is None:
        return None
    return round(number, digits)


def _truncate(text: str | None, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _compact_snapshot(snapshot: Any, limit: int = 1800) -> str:
    if not snapshot:
        return "{}"
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            return _truncate(snapshot, limit)
    if not isinstance(snapshot, dict):
        return _truncate(str(snapshot), limit)
    preferred = {}
    prefixes = (
        "RSI", "MACD", "MACDh", "ADX", "CHOP", "ATR", "ATRr", "SMA_",
        "EMA_", "BB", "VWAP", "PSAR", "CK_STOP", "AL_", "TSI", "RVI",
    )
    for key, value in snapshot.items():
        if any(str(key).startswith(prefix) for prefix in prefixes):
            preferred[key] = value
    if not preferred:
        preferred = dict(list(snapshot.items())[:30])
    return _truncate(json.dumps(preferred, ensure_ascii=False, separators=(",", ":"), default=_json_default), limit)


def _normalize_match_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower().replace("ё", "е")).strip()


def _split_news_keywords(value: str | None) -> list[str]:
    terms: list[str] = []
    for raw in re.split(r"[,;|]", value or ""):
        term = _normalize_match_text(raw)
        if len(term) >= 3 and term not in GENERIC_NEWS_TERMS:
            terms.append(term)
    return terms


def _term_matches_text(term: str, text: str) -> bool:
    if not term or not text:
        return False
    if re.fullmatch(r"[a-z0-9_]{2,12}", term):
        return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None
    return term in text


def load_instrument_match_terms(conn) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT secid, issuer_name, news_keywords
            FROM ref.instrument
            WHERE active = TRUE
              AND secid IS NOT NULL
            """
        )
        rows = []
        for row in cur.fetchall():
            secid = str(row["secid"]).strip()
            terms = {_normalize_match_text(secid)}
            issuer = _normalize_match_text(row.get("issuer_name"))
            if len(issuer) >= 4 and issuer not in GENERIC_NEWS_TERMS:
                terms.add(issuer)
            terms.update(_split_news_keywords(row.get("news_keywords")))
            rows.append({"secid": secid, "terms": sorted(terms, key=len, reverse=True)})
        return rows


def infer_news_secids(
    row: dict[str, Any],
    instrument_terms: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    existing = [str(item).strip() for item in (row.get("secids") or []) if str(item or "").strip()]
    if existing:
        return sorted(set(existing)), ["db"], []

    if not instrument_terms:
        return [], [], []

    text = _normalize_match_text(
        " ".join(
            str(row.get(field) or "")
            for field in ("title", "summary", "content", "external_id")
        )
    )
    matches: list[tuple[int, str, str]] = []
    for instrument in instrument_terms:
        secid = instrument["secid"]
        for term in instrument["terms"]:
            if _term_matches_text(term, text):
                matches.append((len(term), secid, term))
                break

    matches.sort(reverse=True)
    secids: list[str] = []
    terms: list[str] = []
    for _, secid, term in matches:
        if secid in secids:
            continue
        secids.append(secid)
        terms.append(term)
        if len(secids) >= MAX_NEWS_INFERRED_SECIDS:
            break
    return secids, (["keywords"] if secids else []), terms


class EmbeddingClient:
    def __init__(self, provider: str = EMBEDDING_PROVIDER):
        self.provider = provider
        self._fastembed_model = None
        self._dimension: int | None = None
        self.cache_dir = "/tmp/trading_cache/embeddings"
        self.cache_ttl_seconds = 600  # 10 минут

    def _get_cache_path(self, text: str) -> str:
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{self.provider}_{text_hash}.json")

    def _load_from_cache(self, cache_path: str) -> list[float] | None:
        if not os.path.exists(cache_path):
            return None
        try:
            mtime = os.path.getmtime(cache_path)
            if time.time() - mtime > self.cache_ttl_seconds:
                return None
            with open(cache_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_to_cache(self, cache_path: str, vector: list[float]) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(vector, f)
        except Exception:
            pass

    @property
    def model_id(self) -> str:
        if self.provider == "hash":
            return f"hash-{HASH_VECTOR_SIZE}"
        return EMBEDDING_MODEL

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed("dimension probe"))
        return self._dimension

    def embed(self, text: str) -> list[float]:
        clean_text = _truncate(text, MAX_EMBED_TEXT_CHARS)
        
        # Попытка загрузки из кеша
        cache_path = self._get_cache_path(clean_text)
        cached_vector = self._load_from_cache(cache_path)
        if cached_vector:
            return cached_vector

        if self.provider == "hash":
            vector = self._hash_embedding(clean_text)
        elif self.provider == "fastembed":
            vector = self._fastembed_embedding(clean_text)
        else:
            vector = self._ollama_embedding(clean_text)
        
        # Сохранение в кеш
        self._save_to_cache(cache_path, vector)
        return vector

    def _ollama_embedding(self, text: str) -> list[float]:
        response = requests.post(
            OLLAMA_URL,
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=float(os.getenv("AI_RAG_OLLAMA_TIMEOUT_SECONDS", "30")),
        )
        response.raise_for_status()
        vector = response.json().get("embedding")
        if not isinstance(vector, list) or not vector:
            raise RuntimeError("Ollama returned empty embedding")
        return [float(item) for item in vector]

    def _fastembed_embedding(self, text: str) -> list[float]:
        try:
            from fastembed import TextEmbedding
        except Exception as exc:
            raise RuntimeError("fastembed is not installed") from exc
        if self._fastembed_model is None:
            self._fastembed_model = TextEmbedding(model_name=EMBEDDING_MODEL)
        vector = next(self._fastembed_model.embed([text]))
        return [float(item) for item in vector]

    def _hash_embedding(self, text: str) -> list[float]:
        vector = [0.0] * HASH_VECTOR_SIZE
        tokens = re.findall(r"[A-Za-zА-Яа-я0-9_]{2,}", text.lower())
        if not tokens:
            tokens = [text.lower()[:64] or "empty"]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            idx = value % HASH_VECTOR_SIZE
            sign = 1.0 if ((value >> 8) & 1) else -1.0
            vector[idx] += sign
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]


class QdrantMemoryClient:
    def __init__(self, base_url: str = QDRANT_URL):
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            timeout=QDRANT_TIMEOUT,
            **kwargs,
        )
        if response.status_code == 404:
            raise KeyError(path)
        response.raise_for_status()
        return response.json()

    def collection_info(self, collection: str) -> dict[str, Any] | None:
        try:
            return self.request("GET", f"/collections/{collection}").get("result") or {}
        except KeyError:
            return None

    def collection_exists(self, collection: str) -> bool:
        return self.collection_info(collection) is not None

    def ensure_collection(self, collection: str, vector_size: int) -> None:
        info = self.collection_info(collection)
        if info:
            vectors = (((info.get("config") or {}).get("params") or {}).get("vectors") or {})
            existing_size = vectors.get("size") if isinstance(vectors, dict) else None
            if existing_size and int(existing_size) != int(vector_size):
                raise RuntimeError(
                    f"Qdrant collection {collection} vector size mismatch: "
                    f"{existing_size} != {vector_size}"
                )
            return
        self.request(
            "PUT",
            f"/collections/{collection}",
            json={
                "vectors": {"size": vector_size, "distance": "Cosine"},
                "on_disk_payload": True,
            },
        )

    def delete_collection(self, collection: str) -> None:
        try:
            self.request("DELETE", f"/collections/{collection}")
        except KeyError:
            return

    def retrieve_payloads(self, collection: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids or not self.collection_exists(collection):
            return {}
        payload = self.request(
            "POST",
            f"/collections/{collection}/points",
            json={"ids": ids, "with_payload": True, "with_vector": False},
        )
        result = {}
        for point in payload.get("result") or []:
            result[str(point.get("id"))] = point.get("payload") or {}
        return result

    def upsert_points(self, collection: str, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        self.request("PUT", f"/collections/{collection}/points?wait=true", json={"points": points})

    def scroll_ids(self, collection: str, *, page_size: int = 256) -> list[str]:
        if not self.collection_exists(collection):
            return []
        ids: list[str] = []
        offset = None
        while True:
            body: dict[str, Any] = {
                "limit": page_size,
                "with_payload": False,
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            payload = self.request("POST", f"/collections/{collection}/points/scroll", json=body).get("result") or {}
            points = payload.get("points") or []
            ids.extend(str(point.get("id")) for point in points if point.get("id") is not None)
            offset = payload.get("next_page_offset")
            if offset is None or not points:
                break
        return ids

    def delete_points(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        self.request(
            "POST",
            f"/collections/{collection}/points/delete?wait=true",
            json={"points": ids},
        )

    def search(
        self,
        collection: str,
        vector: list[float],
        *,
        limit: int = 5,
        query_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        if not self.collection_exists(collection):
            return []
        body: dict[str, Any] = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if query_filter:
            body["filter"] = query_filter
        if score_threshold is not None:
            body["score_threshold"] = score_threshold
        payload = self.request("POST", f"/collections/{collection}/points/search", json=body)
        return payload.get("result") or []


def connect():
    return psycopg2.connect(**DB_CONFIG)


def load_trade_setup_rows(conn, *, lookback_days: int, limit: int) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            WITH exits AS (
                SELECT *
                FROM trading.journal
                WHERE upper(action) IN ('SELL', 'COVER')
                  AND created_at >= now() - (%s || ' days')::interval
            )
            SELECT
                e.id AS exit_id,
                e.trader_name,
                e.secid,
                upper(e.action) AS close_action,
                e.quantity AS close_qty,
                e.price::numeric AS close_price,
                e.reason AS close_reason,
                e.model_id AS close_model_id,
                e.created_at AS close_time,
                o.id AS open_id,
                upper(o.action) AS open_action,
                o.quantity AS open_qty,
                o.price::numeric AS open_price,
                o.reason AS open_reason,
                o.model_id AS open_model_id,
                o.indicators_snapshot,
                o.created_at AS open_time,
                CASE
                    WHEN upper(e.action) = 'SELL' AND o.price > 0
                    THEN ((e.price / o.price) - 1) * 100
                    WHEN upper(e.action) = 'COVER' AND o.price > 0
                    THEN ((o.price / e.price) - 1) * 100
                    ELSE NULL
                END::numeric AS pnl_pct
            FROM exits e
            JOIN LATERAL (
                SELECT *
                FROM trading.journal o
                WHERE o.trader_name = e.trader_name
                  AND o.secid = e.secid
                  AND upper(o.action) = CASE WHEN upper(e.action) = 'SELL' THEN 'BUY' ELSE 'SHORT' END
                  AND o.created_at < e.created_at
                ORDER BY o.created_at DESC
                LIMIT 1
            ) o ON true
            ORDER BY e.created_at DESC
            LIMIT %s
            """,
            (lookback_days, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def trade_setup_document(row: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    pnl_pct = _round(row.get("pnl_pct"), 3)
    outcome = "win" if (pnl_pct or 0) > 0 else "loss"
    holding_minutes = None
    if row.get("open_time") and row.get("close_time"):
        holding_minutes = int((row["close_time"] - row["open_time"]).total_seconds() // 60)
    source_key = f"trade_setup:{row.get('open_id')}:{row.get('exit_id')}"
    indicators = _compact_snapshot(row.get("indicators_snapshot"))
    text = (
        f"Trade setup outcome={outcome} pnl_pct={pnl_pct}. "
        f"Trader={row.get('trader_name')} secid={row.get('secid')} "
        f"path={row.get('open_action')}->{row.get('close_action')} "
        f"open_price={_round(row.get('open_price'), 4)} close_price={_round(row.get('close_price'), 4)} "
        f"holding_minutes={holding_minutes}. "
        f"Open reason: {_truncate(row.get('open_reason'), 700)}. "
        f"Close reason: {_truncate(row.get('close_reason'), 400)}. "
        f"Indicators: {indicators}"
    )
    payload = {
        "kind": "trade_setup",
        "source_key": source_key,
        "trader": row.get("trader_name"),
        "secid": row.get("secid"),
        "outcome": outcome,
        "pnl_pct": pnl_pct,
        "open_action": row.get("open_action"),
        "close_action": row.get("close_action"),
        "open_time": row.get("open_time").isoformat() if row.get("open_time") else None,
        "close_time": row.get("close_time").isoformat() if row.get("close_time") else None,
        "holding_minutes": holding_minutes,
        "open_reason": _truncate(row.get("open_reason"), 700),
        "close_reason": _truncate(row.get("close_reason"), 400),
        "open_model_id": row.get("open_model_id"),
        "close_model_id": row.get("close_model_id"),
        "embedding_model": EMBEDDING_MODEL,
    }
    payload["source_hash"] = source_hash(text, payload)
    return source_key, payload, text


def load_news_rows(conn, *, lookback_hours: int, limit: int) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                n.news_id,
                n.source,
                n.external_id,
                n.published_at,
                n.title,
                n.link,
                n.summary,
                n.content,
                COALESCE(array_agg(DISTINCT i.secid) FILTER (WHERE i.secid IS NOT NULL), ARRAY[]::text[]) AS secids
            FROM raw.news_item n
            LEFT JOIN raw.news_instrument_match m ON m.news_id = n.news_id
            LEFT JOIN ref.instrument i ON i.instrument_id = m.instrument_id
            WHERE COALESCE(n.published_at, n.ingested_at) >= now() - (%s || ' hours')::interval
              AND COALESCE(n.title, n.summary, n.content, '') <> ''
            GROUP BY n.news_id
            ORDER BY COALESCE(n.published_at, n.ingested_at) DESC NULLS LAST
            LIMIT %s
            """,
            (lookback_hours, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def news_document(
    row: dict[str, Any],
    instrument_terms: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], str]:
    source_key = f"market_news:{row.get('news_id')}"
    published_at = row.get("published_at")
    published_ts = int(published_at.timestamp()) if published_at else None
    body = row.get("summary") or row.get("content") or ""
    secids, match_sources, matched_terms = infer_news_secids(row, instrument_terms)
    text = (
        f"Market news source={row.get('source')} published_at={published_at} "
        f"secids={','.join(secids)} match={','.join(match_sources)} "
        f"title={_truncate(row.get('title'), 300)}. "
        f"Summary: {_truncate(body, 1200)}"
    )
    payload = {
        "kind": "market_news",
        "source_key": source_key,
        "news_id": row.get("news_id"),
        "source": row.get("source"),
        "external_id": row.get("external_id"),
        "published_at": published_at.isoformat() if published_at else None,
        "published_ts": published_ts,
        "title": _truncate(row.get("title"), 300),
        "summary": _truncate(body, 900),
        "link": row.get("link"),
        "secids": secids,
        "match_sources": match_sources,
        "matched_terms": matched_terms[:MAX_NEWS_INFERRED_SECIDS],
        "embedding_model": EMBEDDING_MODEL,
    }
    payload["source_hash"] = source_hash(text, payload)
    return source_key, payload, text


def _window_value(item: dict[str, Any], window_name: str, field: str):
    window = ((item or {}).get("windows") or {}).get(window_name) or {}
    return window.get(field)


def _top_by_metric(context: dict[str, Any], metric: str, limit: int, reverse: bool = True) -> list[dict[str, Any]]:
    rows = []
    for secid, item in context.items():
        value = _number(item.get(metric))
        if value is None:
            continue
        rows.append(
            {
                "secid": secid,
                "value": round(value, 3),
                "price": _round(item.get("price"), 4),
                "issuer": item.get("issuer_name"),
            }
        )
    rows.sort(key=lambda row: row["value"], reverse=reverse)
    return rows[:limit]


def _liquidity_rows(context: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = []
    for secid, item in context.items():
        day_value = _number(_window_value(item, "current_day", "value"))
        if day_value is None:
            continue
        rows.append(
            {
                "secid": secid,
                "value_mrub": round(day_value / 1_000_000, 2),
                "day": _round(item.get("day_change"), 3),
                "price": _round(item.get("price"), 4),
            }
        )
    rows.sort(key=lambda row: row["value_mrub"], reverse=True)
    return rows[:limit]


def _market_snapshot_documents(conn, *, symbol_limit: int = 20) -> list[tuple[str, dict[str, Any], str]]:
    context = load_market_context(conn)
    if not context:
        return []

    latest_update = max(
        (item.get("updated_at") for item in context.values() if item.get("updated_at")),
        default=None,
    )
    regime = latest_market_regime(conn, max_age_minutes=int(os.getenv("AI_RAG_REGIME_MAX_AGE_MINUTES", "180")))
    regime_payload = compact_regime(regime)
    gainers = _top_by_metric(context, "day_change", 6, reverse=True)
    losers = _top_by_metric(context, "day_change", 6, reverse=False)
    hour_movers = _top_by_metric(context, "hour_change", 6, reverse=True)
    liquid = _liquidity_rows(context, 8)
    source_key = "market_snapshot:latest"
    text = (
        f"MOEX market snapshot latest_update={latest_update} "
        f"regime={json.dumps(regime_payload, ensure_ascii=False, separators=(',', ':'), default=_json_default)}. "
        f"Top gainers={json.dumps(gainers, ensure_ascii=False, separators=(',', ':'), default=_json_default)}. "
        f"Top losers={json.dumps(losers, ensure_ascii=False, separators=(',', ':'), default=_json_default)}. "
        f"Hour movers={json.dumps(hour_movers, ensure_ascii=False, separators=(',', ':'), default=_json_default)}. "
        f"Liquidity leaders={json.dumps(liquid, ensure_ascii=False, separators=(',', ':'), default=_json_default)}."
    )
    payload = {
        "kind": "market_snapshot",
        "source_key": source_key,
        "scope": "market",
        "latest_update": latest_update,
        "regime": regime_payload,
        "top_gainers": gainers,
        "top_losers": losers,
        "hour_movers": hour_movers,
        "liquidity_leaders": liquid,
        "embedding_model": EMBEDDING_MODEL,
    }
    payload["source_hash"] = source_hash(text, payload)
    documents = [(source_key, payload, text)]

    focus = {
        item.strip().upper()
        for item in os.getenv(
            "AI_RAG_SNAPSHOT_FOCUS",
            "SBER,GAZP,LKOH,ROSN,MOEX,YNDX,AFLT,GMKN,NVTK,TATN,CHMF,ALRS",
        ).split(",")
        if item.strip()
    }
    ranked_symbols = []
    for secid, item in context.items():
        day = abs(_number(item.get("day_change")) or 0.0)
        hour = abs(_number(item.get("hour_change")) or 0.0)
        value = _number(_window_value(item, "current_day", "value")) or 0.0
        focus_bonus = 10_000_000_000 if secid.upper() in focus else 0
        ranked_symbols.append((focus_bonus + value + (day + hour) * 1_000_000, secid, item))
    ranked_symbols.sort(reverse=True)

    for _, secid, item in ranked_symbols[:symbol_limit]:
        symbol_source_key = f"market_snapshot_symbol:{secid}"
        symbol_payload = {
            "kind": "market_snapshot",
            "source_key": symbol_source_key,
            "scope": "symbol",
            "secid": secid,
            "issuer": item.get("issuer_name"),
            "price": _round(item.get("price"), 4),
            "day_change": _round(item.get("day_change"), 3),
            "hour_change": _round(item.get("hour_change"), 3),
            "five_min_change": _round(item.get("five_min_change"), 3),
            "day_value_mrub": _round((_number(_window_value(item, "current_day", "value")) or 0) / 1_000_000, 2),
            "hour_value_mrub": _round((_number(_window_value(item, "current_hour", "value")) or 0) / 1_000_000, 2),
            "latest_update": item.get("updated_at"),
            "embedding_model": EMBEDDING_MODEL,
        }
        symbol_text = (
            f"MOEX symbol snapshot {secid} {item.get('issuer_name') or ''}: "
            f"price={symbol_payload['price']} day={symbol_payload['day_change']}% "
            f"hour={symbol_payload['hour_change']}% five_min={symbol_payload['five_min_change']}% "
            f"day_value_mrub={symbol_payload['day_value_mrub']} hour_value_mrub={symbol_payload['hour_value_mrub']} "
            f"updated={item.get('updated_at')}."
        )
        symbol_payload["source_hash"] = source_hash(symbol_text, symbol_payload)
        documents.append((symbol_source_key, symbol_payload, symbol_text))
    return documents


def _upsert_documents(
    qdrant: QdrantMemoryClient,
    embedder: EmbeddingClient,
    collection: str,
    documents: list[tuple[str, dict[str, Any], str]],
    *,
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 64,
) -> dict[str, int]:
    ids = [stable_point_id(source_key) for source_key, _, _ in documents]
    existing = qdrant.retrieve_payloads(collection, ids)
    stats = {"seen": len(documents), "indexed": 0, "skipped": 0, "deleted": 0}
    batch: list[dict[str, Any]] = []
    for idx, (source_key, payload, text) in enumerate(documents):
        point_id = ids[idx]
        if not force and existing.get(point_id, {}).get("source_hash") == payload.get("source_hash"):
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["indexed"] += 1
            continue
        batch.append({"id": point_id, "vector": embedder.embed(text), "payload": payload})
        if len(batch) >= batch_size:
            qdrant.upsert_points(collection, batch)
            stats["indexed"] += len(batch)
            batch = []
    if batch:
        qdrant.upsert_points(collection, batch)
        stats["indexed"] += len(batch)
    if not dry_run:
        current_ids = set(ids)
        stale_ids = [point_id for point_id in qdrant.scroll_ids(collection) if point_id not in current_ids]
        if stale_ids:
            qdrant.delete_points(collection, stale_ids)
            stats["deleted"] = len(stale_ids)
    return stats


def index_hybrid_memory(
    *,
    mode: str = "all",
    lookback_days: int = 30,
    news_lookback_hours: int = 168,
    limit: int = 500,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    qdrant = QdrantMemoryClient()
    embedder = EmbeddingClient()
    vector_size = embedder.dimension
    stats: dict[str, Any] = {
        "mode": mode,
        "embedding_provider": embedder.provider,
        "embedding_model": embedder.model_id,
        "vector_size": vector_size,
        "dry_run": dry_run,
    }
    conn = connect()
    try:
        if mode in {"all", "setups"}:
            qdrant.ensure_collection(TRADE_SETUPS_COLLECTION, vector_size)
            rows = load_trade_setup_rows(conn, lookback_days=lookback_days, limit=limit)
            documents = [trade_setup_document(row) for row in rows if row.get("pnl_pct") is not None]
            stats["setups"] = _upsert_documents(
                qdrant, embedder, TRADE_SETUPS_COLLECTION, documents, force=force, dry_run=dry_run
            )
        if mode in {"all", "news"}:
            qdrant.ensure_collection(MARKET_NEWS_COLLECTION, vector_size)
            rows = load_news_rows(conn, lookback_hours=news_lookback_hours, limit=limit)
            instrument_terms = load_instrument_match_terms(conn)
            documents = [news_document(row, instrument_terms) for row in rows]
            stats["news"] = _upsert_documents(
                qdrant, embedder, MARKET_NEWS_COLLECTION, documents, force=force, dry_run=dry_run
            )
            stats["news"]["matched"] = sum(1 for _, payload, _ in documents if payload.get("secids"))
            stats["news"]["keyword_matched"] = sum(
                1 for _, payload, _ in documents if "keywords" in (payload.get("match_sources") or [])
            )
        if mode in {"all", "market"}:
            qdrant.ensure_collection(MARKET_SNAPSHOTS_COLLECTION, vector_size)
            symbol_limit = int(os.getenv("AI_RAG_SNAPSHOT_SYMBOL_LIMIT", "20"))
            documents = _market_snapshot_documents(conn, symbol_limit=symbol_limit)
            stats["market"] = _upsert_documents(
                qdrant, embedder, MARKET_SNAPSHOTS_COLLECTION, documents, force=force, dry_run=dry_run
            )
    finally:
        conn.close()
    return stats


def _kind_filter(kind: str, *, min_ts: int | None = None) -> dict[str, Any]:
    must: list[dict[str, Any]] = [{"key": "kind", "match": {"value": kind}}]
    if min_ts is not None:
        must.append({"key": "published_ts", "range": {"gte": min_ts}})
    return {"must": must}


def _candidate_query_text(
    trader_name: str,
    strategy: str,
    market_features: dict[str, Any],
    positions: list[dict[str, Any]] | None,
    recent_history: list[str] | None,
    market_regime: str | None,
) -> str:
    symbols = []
    for secid, features in list((market_features or {}).items())[:12]:
        symbols.append(f"{secid}:{json.dumps(features, ensure_ascii=False, separators=(',', ':'), default=_json_default)}")
    return _truncate(
        " ".join(
            [
                f"Trader={trader_name}. Strategy={strategy}. Market regime={market_regime}.",
                f"Candidates={' | '.join(symbols)}.",
                f"Positions={json.dumps(positions or [], ensure_ascii=False, default=_json_default)}.",
                f"Recent history={'; '.join(recent_history or [])}.",
            ]
        ),
        MAX_EMBED_TEXT_CHARS,
    )


def _format_setup_hit(hit: dict[str, Any]) -> str:
    payload = hit.get("payload") or {}
    pnl = payload.get("pnl_pct")
    sign = "+" if payload.get("outcome") == "win" else "-"
    reason = _truncate(payload.get("open_reason"), 48)
    close_reason = _truncate(payload.get("close_reason"), 32)
    return (
        f"- {payload.get('secid')} {payload.get('open_action')}->{payload.get('close_action')} "
        f"{sign}{abs(float(pnl or 0)):.2f}% {payload.get('trader')}: "
        f"in={reason}; out={close_reason}"
    )


def _format_news_hit(hit: dict[str, Any]) -> str:
    payload = hit.get("payload") or {}
    secids = ",".join(payload.get("secids") or []) or "market"
    title = _truncate(payload.get("title"), 72)
    published = str(payload.get("published_at") or "")[:10] or "no_date"
    return f"- {published} {secids}: {title}"


def _format_market_hit(hit: dict[str, Any]) -> str:
    payload = hit.get("payload") or {}
    if payload.get("scope") == "symbol":
        return (
            f"- {payload.get('secid')}: p={payload.get('price')} "
            f"d={payload.get('day_change')}% h={payload.get('hour_change')}% "
            f"liq={payload.get('day_value_mrub')}mrub"
        )
    regime = payload.get("regime") or {}
    gainers = ",".join(item.get("secid", "") for item in (payload.get("top_gainers") or [])[:3])
    losers = ",".join(item.get("secid", "") for item in (payload.get("top_losers") or [])[:3])
    liquid = ",".join(item.get("secid", "") for item in (payload.get("liquidity_leaders") or [])[:3])
    return (
        f"- market regime={regime.get('regime')} risk={regime.get('risk')} "
        f"breadth={regime.get('breadth')} up={gainers} down={losers} liq={liquid}"
    )


def _rank_setup_hits(hits: list[dict[str, Any]], secids: set[str], limit: int) -> list[dict[str, Any]]:
    def key(hit):
        payload = hit.get("payload") or {}
        same_symbol = 1 if payload.get("secid") in secids else 0
        return (same_symbol, float(hit.get("score") or 0))
    return sorted(hits, key=key, reverse=True)[:limit]


def _filter_news_hits(hits: list[dict[str, Any]], secids: set[str], limit: int) -> list[dict[str, Any]]:
    selected = []
    general = []
    for hit in hits:
        payload = hit.get("payload") or {}
        hit_secids = set(payload.get("secids") or [])
        if hit_secids and hit_secids.intersection(secids):
            selected.append(hit)
        elif not hit_secids:
            general.append(hit)
    return (selected + general)[:limit]


def _rank_market_hits(hits: list[dict[str, Any]], secids: set[str], limit: int) -> list[dict[str, Any]]:
    def key(hit):
        payload = hit.get("payload") or {}
        same_symbol = 1 if payload.get("secid") in secids else 0
        market_scope = 1 if payload.get("scope") == "market" else 0
        return (market_scope, same_symbol, float(hit.get("score") or 0))

    return sorted(hits, key=key, reverse=True)[:limit]


def build_trader_rag_context(
    *,
    trader_name: str,
    strategy: str,
    market_features: dict[str, Any],
    positions: list[dict[str, Any]] | None = None,
    recent_history: list[str] | None = None,
    market_regime: str | None = None,
    log_func=None,
) -> str:
    if os.getenv("AI_RAG_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
        return ""
    try:
        setup_limit = int(os.getenv("AI_RAG_SETUPS_LIMIT", "3"))
        news_limit = int(os.getenv("AI_RAG_NEWS_LIMIT", "3"))
        market_limit = int(os.getenv("AI_RAG_MARKET_LIMIT", "1"))
        score_threshold = os.getenv("AI_RAG_SCORE_THRESHOLD")
        min_score = float(score_threshold) if score_threshold else None
        news_max_age_hours = int(os.getenv("AI_RAG_NEWS_MAX_AGE_HOURS", "168"))
        qdrant = QdrantMemoryClient()
        embedder = EmbeddingClient()
        query_text = _candidate_query_text(
            trader_name, strategy, market_features, positions, recent_history, market_regime
        )
        query_vector = embedder.embed(query_text)
        secids = set((market_features or {}).keys())
        setup_hits = qdrant.search(
            TRADE_SETUPS_COLLECTION,
            query_vector,
            limit=max(setup_limit * 4, setup_limit),
            query_filter=_kind_filter("trade_setup"),
            score_threshold=min_score,
        )
        setup_hits = _rank_setup_hits(setup_hits, secids, setup_limit)
        min_news_ts = int((datetime.now(timezone.utc) - timedelta(hours=news_max_age_hours)).timestamp())
        news_hits = qdrant.search(
            MARKET_NEWS_COLLECTION,
            query_vector,
            limit=max(news_limit * 6, news_limit),
            query_filter=_kind_filter("market_news", min_ts=min_news_ts),
            score_threshold=min_score,
        )
        news_hits = _filter_news_hits(news_hits, secids, news_limit)
        market_hits: list[dict[str, Any]] = []
        if market_limit > 0:
            market_hits = qdrant.search(
                MARKET_SNAPSHOTS_COLLECTION,
                query_vector,
                limit=max(market_limit * 10, 10),
                query_filter=_kind_filter("market_snapshot"),
                score_threshold=min_score,
            )
            aggregate_payload = qdrant.retrieve_payloads(
                MARKET_SNAPSHOTS_COLLECTION,
                [stable_point_id("market_snapshot:latest")],
            ).get(stable_point_id("market_snapshot:latest"))
            if aggregate_payload and not any(
                (hit.get("payload") or {}).get("source_key") == "market_snapshot:latest"
                for hit in market_hits
            ):
                market_hits.append({"payload": aggregate_payload, "score": 1.0})
            market_hits = _rank_market_hits(market_hits, secids, market_limit)

        parts = []
        if market_hits:
            parts.append("RAG_MARKET compact snapshot:")
            parts.extend(_format_market_hit(hit) for hit in market_hits)
        if news_hits:
            parts.append("RAG_NEWS fresh risk context:")
            parts.extend(_format_news_hit(hit) for hit in news_hits)
        if setup_hits:
            parts.append("RAG_TRADES history, not command:")
            parts.extend(_format_setup_hit(hit) for hit in setup_hits)
        if not parts:
            return ""
        parts.append("Rule: use only as extra risk context with MKT.")
        context = _truncate("\n".join(parts), MAX_RAG_CONTEXT_CHARS)
        if log_func:
            log_func(
                f"[{trader_name}] Hybrid RAG: setups={len(setup_hits)} "
                f"news={len(news_hits)} market={len(market_hits)} chars={len(context)}"
            )
        return context
    except Exception as exc:
        if log_func:
            log_func(f"[{trader_name}] Hybrid RAG unavailable: {exc}")
        return ""
