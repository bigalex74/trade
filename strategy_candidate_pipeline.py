#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any

import psycopg2
import psycopg2.extras


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

DDL = """
CREATE TABLE IF NOT EXISTS trading.strategy_candidates (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    source TEXT NOT NULL,
    trader_name TEXT,
    title TEXT NOT NULL,
    candidate_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    validation_status TEXT NOT NULL DEFAULT 'PENDING',
    backtest_run_id BIGINT,
    promoted_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS strategy_candidates_status_created_idx
    ON trading.strategy_candidates (status, created_at DESC);
CREATE INDEX IF NOT EXISTS strategy_candidates_trader_created_idx
    ON trading.strategy_candidates (trader_name, created_at DESC);
"""


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def create_candidate(
    conn,
    *,
    source: str,
    title: str,
    candidate_text: str,
    trader_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trading.strategy_candidates
                (source, trader_name, title, candidate_text, metadata)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (source, trader_name, title[:300], candidate_text, psycopg2.extras.Json(metadata or {})),
        )
        candidate_id = cur.fetchone()[0]
    conn.commit()
    return candidate_id


if __name__ == "__main__":
    conn = get_db_connection()
    try:
        ensure_schema(conn)
        print("strategy_candidates schema ready")
    finally:
        conn.close()
