#!/usr/bin/env python3
from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import psycopg2
import psycopg2.extras


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def load_trader_weights(conn) -> dict[str, float]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trader_name, tuning_score, ai_failure_rate_pct
            FROM trading.trader_performance_v
            WHERE trader_name IS NOT NULL
            """
        )
        weights = {}
        for trader_name, tuning_score, ai_failure_rate_pct in cur.fetchall():
            if trader_name == "Meta_Oracle":
                continue
            score = _float(tuning_score)
            failure_penalty = min(0.7, max(0.0, _float(ai_failure_rate_pct) / 100))
            weight = max(0.1, 1.0 + (score / 10.0)) * (1.0 - failure_penalty)
            weights[trader_name] = round(weight, 4)
    return weights


def load_weighted_consensus(conn, lookback_hours: int = 24, limit: int = 12) -> list[dict[str, Any]]:
    weights = load_trader_weights(conn)
    if not weights:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT trader_name, secid, upper(action) AS action, quantity, price, created_at
            FROM trading.journal
            WHERE trader_name = ANY(%s)
              AND created_at > clock_timestamp() - (%s || ' hours')::interval
              AND upper(action) IN ('BUY', 'SELL')
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (list(weights), lookback_hours),
        )
        rows = cur.fetchall()

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "buy_weight": 0.0,
        "sell_weight": 0.0,
        "traders": set(),
        "last_at": None,
    })
    for row in rows:
        secid = row["secid"]
        weight = weights.get(row["trader_name"], 0.1)
        item = grouped[secid]
        item["traders"].add(row["trader_name"])
        item["last_at"] = max(item["last_at"], row["created_at"]) if item["last_at"] else row["created_at"]
        if row["action"] == "BUY":
            item["buy_weight"] += weight
        else:
            item["sell_weight"] += weight

    consensus = []
    for secid, item in grouped.items():
        total = item["buy_weight"] + item["sell_weight"]
        net = item["buy_weight"] - item["sell_weight"]
        if total <= 0:
            continue
        consensus.append({
            "secid": secid,
            "net_score": round(net, 4),
            "buy_weight": round(item["buy_weight"], 4),
            "sell_weight": round(item["sell_weight"], 4),
            "confidence": round(abs(net) / total, 4),
            "traders": sorted(item["traders"]),
            "last_at": item["last_at"].isoformat() if item["last_at"] else None,
        })
    consensus.sort(key=lambda item: (abs(item["net_score"]), item["confidence"]), reverse=True)
    return consensus[:limit]


if __name__ == "__main__":
    conn = get_db_connection()
    try:
        import json
        print(json.dumps(load_weighted_consensus(conn), ensure_ascii=False, indent=2))
    finally:
        conn.close()
