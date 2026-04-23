#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from statistics import mean
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
CREATE TABLE IF NOT EXISTS analytics.market_regime (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    engine TEXT NOT NULL,
    regime TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_multiplier NUMERIC NOT NULL,
    breadth_pct NUMERIC,
    avg_day_change_pct NUMERIC,
    avg_hour_change_pct NUMERIC,
    avg_intraday_range_pct NUMERIC,
    sample_size INTEGER NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS market_regime_engine_created_idx
    ON analytics.market_regime (engine, created_at DESC);
"""


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _range_pct(windows: dict[str, Any]) -> float | None:
    day = (windows or {}).get("current_day") or {}
    high = _float(day.get("high"))
    low = _float(day.get("low"))
    close = _float(day.get("close"))
    if high is None or low is None or close in (None, 0):
        return None
    return ((high - low) / close) * 100


def calculate_regime(rows: list[dict[str, Any]], engine: str = "stock") -> dict[str, Any]:
    sample = [row for row in rows if row.get("current_price") is not None]
    day_changes = [_float(row.get("day_change_pct")) for row in sample]
    day_changes = [value for value in day_changes if value is not None]
    hour_changes = [_float(row.get("hour_change_pct")) for row in sample]
    hour_changes = [value for value in hour_changes if value is not None]
    ranges = [_range_pct(row.get("windows") or {}) for row in sample]
    ranges = [value for value in ranges if value is not None]

    positive_count = sum(1 for value in day_changes if value > 0)
    breadth_pct = (positive_count / len(day_changes) * 100) if day_changes else None
    avg_day = mean(day_changes) if day_changes else None
    avg_hour = mean(hour_changes) if hour_changes else None
    avg_range = mean(ranges) if ranges else None

    risk_level = "YELLOW"
    risk_multiplier = 0.80
    regime = "mixed"
    if avg_day is not None and breadth_pct is not None:
        if avg_day <= -2.0 or breadth_pct < 25:
            risk_level = "RED"
            risk_multiplier = 0.35
            regime = "risk_off"
        elif avg_day <= -1.0 or breadth_pct < 40:
            risk_level = "ORANGE"
            risk_multiplier = 0.50
            regime = "weak"
        elif avg_day >= 0.5 and breadth_pct >= 65:
            risk_level = "GREEN"
            risk_multiplier = 1.00
            regime = "risk_on"

    return {
        "engine": engine,
        "regime": regime,
        "risk_level": risk_level,
        "risk_multiplier": round(risk_multiplier, 3),
        "breadth_pct": round(breadth_pct, 3) if breadth_pct is not None else None,
        "avg_day_change_pct": round(avg_day, 3) if avg_day is not None else None,
        "avg_hour_change_pct": round(avg_hour, 3) if avg_hour is not None else None,
        "avg_intraday_range_pct": round(avg_range, 3) if avg_range is not None else None,
        "sample_size": len(sample),
        "details": {
            "positive_symbols": positive_count,
            "day_change_points": len(day_changes),
            "range_points": len(ranges),
        },
    }


def refresh_market_regime(conn, engine: str = "stock", dry_run: bool = False) -> dict[str, Any]:
    ensure_schema(conn)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT secid, current_price, day_change_pct, hour_change_pct, five_min_change_pct, windows
            FROM analytics.trader_market_context_v
            WHERE active = TRUE
              AND engine = %s
              AND current_price IS NOT NULL
            """,
            (engine,),
        )
        regime = calculate_regime([dict(row) for row in cur.fetchall()], engine=engine)
        if not dry_run:
            cur.execute(
                """
                INSERT INTO analytics.market_regime
                    (engine, regime, risk_level, risk_multiplier, breadth_pct,
                     avg_day_change_pct, avg_hour_change_pct, avg_intraday_range_pct,
                     sample_size, details)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, created_at
                """,
                (
                    regime["engine"],
                    regime["regime"],
                    regime["risk_level"],
                    regime["risk_multiplier"],
                    regime["breadth_pct"],
                    regime["avg_day_change_pct"],
                    regime["avg_hour_change_pct"],
                    regime["avg_intraday_range_pct"],
                    regime["sample_size"],
                    psycopg2.extras.Json(regime["details"]),
                ),
            )
            row = cur.fetchone()
            regime["id"] = row["id"]
            regime["created_at"] = row["created_at"].isoformat()
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return regime


def latest_market_regime(conn, engine: str = "stock", max_age_minutes: int = 180) -> dict[str, Any] | None:
    ensure_schema(conn)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT *
            FROM analytics.market_regime
            WHERE engine = %s
              AND created_at > clock_timestamp() - (%s || ' minutes')::interval
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (engine, max_age_minutes),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def compact_regime(regime: dict[str, Any] | None) -> dict[str, Any]:
    if not regime:
        return {}
    return {
        "regime": regime.get("regime"),
        "risk": regime.get("risk_level"),
        "risk_mul": _float(regime.get("risk_multiplier")),
        "breadth": _float(regime.get("breadth_pct")),
        "day": _float(regime.get("avg_day_change_pct")),
        "hour": _float(regime.get("avg_hour_change_pct")),
        "range": _float(regime.get("avg_intraday_range_pct")),
        "n": int(regime.get("sample_size") or 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh analytics.market_regime from current MOEX context.")
    parser.add_argument("--engine", default="stock")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    conn = get_db_connection()
    try:
        result = refresh_market_regime(conn, engine=args.engine, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
