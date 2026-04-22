#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import timedelta
from typing import Callable

import psycopg2


DB_CONFIG = {
    "host": os.getenv("AI_JOBS_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("AI_JOBS_DB_NAME", os.getenv("DB_NAME", "market_research")),
    "user": os.getenv("AI_JOBS_DB_USER", os.getenv("DB_USER", "n8n_user")),
    "password": os.getenv("AI_JOBS_DB_PASSWORD", os.getenv("DB_PASSWORD", "n8n_db_password")),
}

DDL = """
CREATE TABLE IF NOT EXISTS trading.ai_context_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    quality_ok BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS ai_context_cache_expires_idx
    ON trading.ai_context_cache (expires_at);
"""

LOW_QUALITY_MARKERS = (
    "analysis failed",
    "incubation failed",
    "ai analysis failed",
    "kb unavailable",
    "kb offline",
    "no context found",
    "no data",
    "not enough information",
    "empty response",
)


def connect():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn=None) -> None:
    own_conn = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def is_low_quality_context(text: str | None) -> bool:
    value = (text or "").strip()
    if len(value) < int(os.getenv("AI_CONTEXT_MIN_CHARS", "40")):
        return True
    lowered = value.lower()
    return any(marker in lowered for marker in LOW_QUALITY_MARKERS)


def get_or_refresh(key: str, ttl_seconds: int, fetch_func: Callable[[], str], fallback: str = "") -> str:
    if os.getenv("AI_CONTEXT_CACHE_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
        value = fetch_func()
        return fallback if is_low_quality_context(value) else value

    try:
        conn = connect()
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT value, quality_ok
                FROM trading.ai_context_cache
                WHERE key = %s
                  AND expires_at > clock_timestamp()
                """,
                (key,),
            )
            row = cur.fetchone()
            if row:
                conn.close()
                return row[0] if row[1] else fallback
    except Exception:
        value = fetch_func()
        return fallback if is_low_quality_context(value) else value

    value = fetch_func()
    quality_ok = not is_low_quality_context(value)
    stored_value = value if value is not None else ""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trading.ai_context_cache (key, value, quality_ok, expires_at, updated_at)
                VALUES (%s, %s, %s, clock_timestamp() + %s::interval, clock_timestamp())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    quality_ok = EXCLUDED.quality_ok,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = clock_timestamp()
                """,
                (key, stored_value, quality_ok, timedelta(seconds=ttl_seconds)),
            )
        conn.commit()
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
    return stored_value if quality_ok else fallback
