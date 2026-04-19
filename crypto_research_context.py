import os
import json
import psycopg2

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME_CRYPTO", "crypto_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

MARKET_CONTEXT_SQL = """
SELECT
    secid,
    instrument_group,
    issuer_name,
    current_price,
    day_change_pct,
    hour_change_pct,
    five_min_change_pct,
    updated_at,
    windows
FROM analytics.trader_market_context_v
WHERE active = TRUE
ORDER BY secid
"""


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def _to_float(value):
    if value is None:
        return None
    return float(value)


def _normalize_windows(windows):
    if windows is None:
        return {}
    if isinstance(windows, str):
        return json.loads(windows)
    return windows


def load_market_context(conn=None):
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        with conn.cursor() as cur:
            cur.execute(MARKET_CONTEXT_SQL)
            rows = cur.fetchall()

        context = {}
        for secid, instrument_group, issuer_name, current_price, day_change_pct, hour_change_pct, five_min_change_pct, updated_at, windows in rows:
            day_change = _to_float(day_change_pct)
            hour_change = _to_float(hour_change_pct)
            five_min_change = _to_float(five_min_change_pct)
            context[secid] = {
                "price": _to_float(current_price),
                "change": next(
                    (
                        value
                        for value in (day_change, hour_change, five_min_change)
                        if value is not None
                    ),
                    0.0,
                ),
                "day_change": day_change,
                "hour_change": hour_change,
                "five_min_change": five_min_change,
                "instrument_group": instrument_group,
                "issuer_name": issuer_name,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "windows": _normalize_windows(windows),
            }
        return context
    finally:
        if close_conn:
            conn.close()


def build_price_snapshot(context):
    snapshot = {}
    for secid, item in context.items():
        price = item.get("price")
        if price is None:
            continue
        snapshot[secid] = {
            "price": price,
            "change": item.get("change") or 0.0,
        }
    return snapshot


def compact_context_payload(item):
    if not item:
        return None

    windows = {}
    for key, value in (item.get("windows") or {}).items():
        if not isinstance(value, dict):
            continue
        windows[key] = {
            field: value.get(field)
            for field in (
                "period_start",
                "period_end",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "value",
                "bars_count",
                "source_interval",
                "is_closed",
                "change_abs",
                "change_pct",
                "updated_at",
            )
            if field in value
        }

    return {
        "price": item.get("price"),
        "day_change": item.get("day_change"),
        "hour_change": item.get("hour_change"),
        "five_min_change": item.get("five_min_change"),
        "instrument_group": item.get("instrument_group"),
        "issuer_name": item.get("issuer_name"),
        "windows": windows,
    }
