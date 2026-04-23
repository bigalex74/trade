#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import requests


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
EMBEDDING_PROVIDER = os.getenv("AI_RAG_EMBEDDING_PROVIDER", "ollama").lower()
OLLAMA_URL = os.getenv("AI_RAG_OLLAMA_URL", "http://localhost:11434/api/embeddings")
EMBEDDING_MODEL = os.getenv("AI_RAG_EMBEDDING_MODEL", "nomic-embed-text")
HASH_VECTOR_SIZE = int(os.getenv("AI_RAG_HASH_VECTOR_SIZE", "768"))
MAX_EMBED_TEXT_CHARS = int(os.getenv("AI_RAG_EMBED_TEXT_MAX_CHARS", "6000"))
MAX_RAG_CONTEXT_CHARS = int(os.getenv("AI_RAG_MAX_CHARS", "700"))
RAG_NAMESPACE = uuid.UUID("b82a89cf-5661-4a4f-9c61-c076e5e78e7b")


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


class EmbeddingClient:
    def __init__(self, provider: str = EMBEDDING_PROVIDER):
        self.provider = provider
        self._fastembed_model = None
        self._dimension: int | None = None

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
        if self.provider == "hash":
            return self._hash_embedding(clean_text)
        if self.provider == "fastembed":
            return self._fastembed_embedding(clean_text)
        return self._ollama_embedding(clean_text)

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


def news_document(row: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    source_key = f"market_news:{row.get('news_id')}"
    published_at = row.get("published_at")
    published_ts = int(published_at.timestamp()) if published_at else None
    body = row.get("summary") or row.get("content") or ""
    secids = [item for item in (row.get("secids") or []) if item]
    text = (
        f"Market news source={row.get('source')} published_at={published_at} "
        f"secids={','.join(secids)} title={_truncate(row.get('title'), 300)}. "
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
        "embedding_model": EMBEDDING_MODEL,
    }
    payload["source_hash"] = source_hash(text, payload)
    return source_key, payload, text


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
            documents = [news_document(row) for row in rows]
            stats["news"] = _upsert_documents(
                qdrant, embedder, MARKET_NEWS_COLLECTION, documents, force=force, dry_run=dry_run
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
    outcome = "плюс" if payload.get("outcome") == "win" else "минус"
    reason = _truncate(payload.get("open_reason"), 190)
    close_reason = _truncate(payload.get("close_reason"), 120)
    return (
        f"- {payload.get('secid')} {payload.get('open_action')}->{payload.get('close_action')} "
        f"{outcome} {pnl:+.2f}% | трейдер {payload.get('trader')} | "
        f"вход: {reason} | выход: {close_reason}"
    )


def _format_news_hit(hit: dict[str, Any]) -> str:
    payload = hit.get("payload") or {}
    secids = ",".join(payload.get("secids") or [])
    title = _truncate(payload.get("title"), 160)
    summary = _truncate(payload.get("summary"), 180)
    published = payload.get("published_at") or "без даты"
    return f"- {published} {payload.get('source')} {secids}: {title}. {summary}"


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

        parts = []
        if setup_hits:
            parts.append("ПАМЯТЬ ПОХОЖИХ СДЕЛОК (исторические исходы, не приказ к действию):")
            parts.extend(_format_setup_hit(hit) for hit in setup_hits)
        if news_hits:
            parts.append("НОВОСТНОЙ КОНТЕКСТ QDRANT (проверь свежесть и не переоценивай одиночную новость):")
            parts.extend(_format_news_hit(hit) for hit in news_hits)
        if not parts:
            return ""
        parts.append("Правило: используй этот блок только как дополнительный риск-контекст вместе с MARKET FEATURES.")
        context = _truncate("\n".join(parts), MAX_RAG_CONTEXT_CHARS)
        if log_func:
            log_func(
                f"[{trader_name}] Hybrid RAG: setups={len(setup_hits)} "
                f"news={len(news_hits)} chars={len(context)}"
            )
        return context
    except Exception as exc:
        if log_func:
            log_func(f"[{trader_name}] Hybrid RAG unavailable: {exc}")
        return ""
