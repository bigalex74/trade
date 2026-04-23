#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import psycopg2
import psycopg2.extras

from gemini_cli_runner import call_ai_json_with_fallback


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "market_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

TRADERS_DNA = {
    "VSA_Victor": "VSA Specialist. Look for volume/price spread signals.",
    "Chaos_Bill": "Chaos Theory. Use Alligator and Fractals.",
    "Elliott_Alex": "Elliott Wave Expert.",
    "Contrarian_Ricardo": "Mean Reversion / Contrarian.",
    "Quant_Diana": "Quantitative / Statistical.",
    "PriceAction_Nikita": "Pure Price Action.",
    "Passive_Palych": "Dividend / Index investor.",
    "Scalper_Kesha": "Ultra Fast Scalper.",
    "Value_Monya": "Value Investor.",
    "Index_Tracker": "Index Mirror.",
    "Meta_Oracle": "Collective Mind. Analyzes other agents.",
}

DDL = """
CREATE TABLE IF NOT EXISTS trading.ai_backtest_runs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    trader_name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    symbols TEXT[] NOT NULL,
    initial_capital NUMERIC NOT NULL,
    final_equity NUMERIC,
    return_pct NUMERIC,
    max_drawdown_pct NUMERIC,
    ai_calls INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS trading.ai_backtest_trades (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES trading.ai_backtest_runs(id) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    trader_name TEXT NOT NULL,
    secid TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price NUMERIC NOT NULL,
    notional NUMERIC NOT NULL,
    commission NUMERIC NOT NULL,
    reason TEXT,
    model_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
"""


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def parse_args():
    parser = argparse.ArgumentParser(description="Safe batched AI backtester for MOEX daily candles.")
    parser.add_argument("--trader", default="Chaos_Bill", choices=sorted(TRADERS_DNA))
    parser.add_argument("--strategy", default=None, help="Override trader strategy text.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbols", default="", help="Comma-separated secids. Default: top liquid symbols.")
    parser.add_argument("--max-symbols", type=int, default=int(os.getenv("AI_BACKTEST_MAX_SYMBOLS", "12")))
    parser.add_argument("--max-days", type=int, default=int(os.getenv("AI_BACKTEST_MAX_DAYS", "10")))
    parser.add_argument("--batch-days", type=int, default=int(os.getenv("AI_BACKTEST_BATCH_DAYS", "5")))
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("AI_BACKTEST_LOOKBACK_DAYS", "20")))
    parser.add_argument("--initial-capital", type=float, default=float(os.getenv("AI_BACKTEST_INITIAL_CAPITAL", "10000")))
    parser.add_argument("--position-fraction", type=float, default=float(os.getenv("AI_BACKTEST_POSITION_FRACTION", "0.1")))
    parser.add_argument("--commission-bps", type=float, default=float(os.getenv("AI_BACKTEST_COMMISSION_BPS", "5")))
    parser.add_argument("--slippage-bps", type=float, default=float(os.getenv("AI_BACKTEST_SLIPPAGE_BPS", "5")))
    parser.add_argument("--execute-ai", action="store_true", help="Actually call Gemini. Default only validates data and prompt shape.")
    parser.add_argument("--save", action="store_true", help="Save run/trades to DB. AI execution is still required for trades.")
    return parser.parse_args()


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def choose_symbols(conn, start_date: date, end_date: date, requested: list[str], max_symbols: int) -> list[str]:
    if requested:
        return requested[:max_symbols]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT secid
            FROM raw.candle
            WHERE engine = 'stock'
              AND interval_name = '1d'
              AND candle_time::date BETWEEN %s AND %s
            GROUP BY secid
            ORDER BY avg(value) DESC NULLS LAST, count(*) DESC, secid ASC
            LIMIT %s
            """,
            (start_date, end_date, max_symbols),
        )
        return [row[0] for row in cur.fetchall()]


def load_daily_bars(conn, symbols: list[str], start_date: date, end_date: date, lookback_days: int):
    from_date = start_date - timedelta(days=max(lookback_days * 2, 40))
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT secid, candle_time::date AS d, open, high, low, close, volume, value
            FROM raw.candle
            WHERE engine = 'stock'
              AND interval_name = '1d'
              AND secid = ANY(%s)
              AND candle_time::date BETWEEN %s AND %s
            ORDER BY secid, candle_time ASC
            """,
            (symbols, from_date, end_date),
        )
        rows = cur.fetchall()
    bars = defaultdict(list)
    by_date = defaultdict(dict)
    for row in rows:
        item = {
            "date": row["d"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"] or 0),
            "value": float(row["value"] or 0),
        }
        bars[row["secid"]].append(item)
        by_date[row["d"]][row["secid"]] = item
    return bars, by_date


def pct(last: float, first: float | None) -> float | None:
    if first in (None, 0):
        return None
    return round(((last / first) - 1) * 100, 3)


def build_features(history: list[dict[str, Any]], target_bar: dict[str, Any]) -> dict[str, Any] | None:
    if len(history) < 5:
        return None
    closes = [bar["close"] for bar in history]
    highs = [bar["high"] for bar in history[-20:]]
    lows = [bar["low"] for bar in history[-20:]]
    volumes = [bar["volume"] for bar in history[-20:]]
    last_close = closes[-1]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    return {
        "prev_close": round(last_close, 4),
        "target_open": round(target_bar["open"], 4),
        "ret_1d_pct": pct(last_close, closes[-2] if len(closes) >= 2 else None),
        "ret_5d_pct": pct(last_close, closes[-6] if len(closes) >= 6 else None),
        "ret_20d_pct": pct(last_close, closes[-21] if len(closes) >= 21 else None),
        "range_20d_pct": pct(max(highs), min(lows)) if highs and lows else None,
        "volume_ratio": round((volumes[-1] / avg_volume), 3) if avg_volume else None,
    }


def build_day_payloads(symbols, bars, by_date, start_date, end_date, lookback_days, max_days):
    payloads = []
    valid_dates = []
    for target_date in date_range(start_date, end_date):
        if len(payloads) >= max_days:
            break
        market = {}
        for secid in symbols:
            target_bar = by_date.get(target_date, {}).get(secid)
            if not target_bar:
                continue
            history = [bar for bar in bars[secid] if bar["date"] < target_date][-lookback_days:]
            features = build_features(history, target_bar)
            if features:
                market[secid] = features
        if market:
            payloads.append({"date": target_date.isoformat(), "market": market})
            valid_dates.append(target_date)
    return payloads, valid_dates


def batched(items, size):
    for index in range(0, len(items), max(1, size)):
        yield items[index:index + max(1, size)]


def build_prompt(trader_name: str, strategy: str, batch_payload: list[dict[str, Any]]) -> str:
    return f"""
    ROLE: Historical MOEX backtest decision engine.
    TRADER: {trader_name}
    STRATEGY: {strategy}

    DATA_RULES:
    - For each target date, use only the per-symbol features provided for that date.
    - target_open is tradable. Future close/high/low for that date is hidden.
    - Keep turnover low. Prefer no action unless the setup fits the strategy.
    - Max 3 actions per date. Long-only for this backtest: buy, sell, hold.

    BATCH_JSON: {json.dumps(batch_payload, ensure_ascii=False)}

    Respond ONLY raw JSON:
    {{"days": [{{"date": "YYYY-MM-DD", "summary": "...", "actions": [{{"secid": "SBER", "action": "buy|sell|hold", "confidence": 0.0, "reason": "..."}}]}}]}}
    """


def normalize_ai_days(result: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(result, dict):
        return {}
    days = result.get("days") or result.get("results") or []
    normalized = {}
    for day in days:
        if not isinstance(day, dict):
            continue
        day_key = str(day.get("date") or "")
        actions = day.get("actions") or []
        if isinstance(actions, list):
            normalized[day_key] = [action for action in actions if isinstance(action, dict)]
    return normalized


def create_run(conn, args, symbols, status="running") -> int | None:
    if not args.save:
        return None
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trading.ai_backtest_runs
                (trader_name, strategy, start_date, end_date, symbols, initial_capital, status, config)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                args.trader,
                args.strategy or TRADERS_DNA[args.trader],
                args.start,
                args.end,
                symbols,
                args.initial_capital,
                status,
                psycopg2.extras.Json(vars(args)),
            ),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def save_trade(conn, run_id, trade_date, trader_name, secid, action, qty, price, commission, reason, model_id):
    if run_id is None:
        return
    notional = qty * price
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trading.ai_backtest_trades
                (run_id, trade_date, trader_name, secid, action, quantity, price, notional, commission, reason, model_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, trade_date, trader_name, secid, action, qty, price, notional, commission, reason, model_id),
        )
    conn.commit()


def update_run(conn, run_id, status, final_equity, initial_capital, equity_curve, ai_calls, summary):
    if run_id is None:
        return
    peak = initial_capital
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, ((value / peak) - 1) * 100)
    return_pct = ((final_equity / initial_capital) - 1) * 100 if initial_capital else 0
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE trading.ai_backtest_runs
            SET final_equity = %s,
                return_pct = %s,
                max_drawdown_pct = %s,
                ai_calls = %s,
                status = %s,
                summary = %s
            WHERE id = %s
            """,
            (final_equity, return_pct, max_dd, ai_calls, status, psycopg2.extras.Json(summary), run_id),
        )
    conn.commit()


def simulate(args, symbols, by_date, day_payloads, conn, run_id):
    cash = float(args.initial_capital)
    positions: dict[str, int] = defaultdict(int)
    equity_curve = []
    ai_calls = 0
    model_ids = []
    decisions_by_date = {}
    strategy = args.strategy or TRADERS_DNA[args.trader]

    if args.execute_ai:
        models = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
        for batch_payload in batched(day_payloads, args.batch_days):
            prompt = build_prompt(args.trader, strategy, batch_payload)
            result, model_id = call_ai_json_with_fallback(
                prompt,
                models,
                name="AIBacktester",
                log_func=print,
                category="backtest",
                trader_name=args.trader,
            )
            ai_calls += 1
            if model_id:
                model_ids.append(model_id)
            decisions_by_date.update(normalize_ai_days(result))
    else:
        first_prompt = build_prompt(args.trader, strategy, day_payloads[: args.batch_days])
        print("DRY RUN: AI calls disabled. First prompt chars:", len(first_prompt))
        print("DRY RUN: days prepared:", len(day_payloads), "symbols:", symbols)

    for payload in day_payloads:
        trade_date = date.fromisoformat(payload["date"])
        actions = decisions_by_date.get(payload["date"], [])[:3] if args.execute_ai else []
        for action in actions:
            secid = str(action.get("secid") or "").upper().strip()
            if secid not in symbols:
                continue
            verb = str(action.get("action") or "hold").lower()
            bar = by_date.get(trade_date, {}).get(secid)
            if not bar or verb == "hold":
                continue
            slip = args.slippage_bps / 10000
            commission_rate = args.commission_bps / 10000
            reason = str(action.get("reason") or "")[:500]
            if verb == "buy":
                equity = cash + sum(qty * by_date.get(trade_date, {}).get(s, {"close": 0})["close"] for s, qty in positions.items())
                budget = min(cash, equity * args.position_fraction)
                price = bar["open"] * (1 + slip)
                qty = int(budget / price)
                if qty <= 0:
                    continue
                notional = qty * price
                commission = notional * commission_rate
                if notional + commission > cash:
                    continue
                cash -= notional + commission
                positions[secid] += qty
                save_trade(conn, run_id, trade_date, args.trader, secid, "BUY", qty, price, commission, reason, model_ids[-1] if model_ids else None)
            elif verb == "sell" and positions.get(secid, 0) > 0:
                qty = positions[secid]
                price = bar["open"] * (1 - slip)
                notional = qty * price
                commission = notional * commission_rate
                cash += notional - commission
                positions[secid] = 0
                save_trade(conn, run_id, trade_date, args.trader, secid, "SELL", qty, price, commission, reason, model_ids[-1] if model_ids else None)

        close_equity = cash
        for secid, qty in positions.items():
            if qty:
                bar = by_date.get(trade_date, {}).get(secid)
                close_equity += qty * (bar["close"] if bar else 0)
        equity_curve.append(close_equity)

    final_equity = equity_curve[-1] if equity_curve else cash
    summary = {
        "symbols": symbols,
        "days": len(day_payloads),
        "model_ids": sorted(set(model_ids)),
        "positions": dict(positions),
    }
    update_run(conn, run_id, "succeeded", final_equity, args.initial_capital, equity_curve, ai_calls, summary)
    return final_equity, equity_curve, ai_calls, summary


def main():
    args = parse_args()
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    if end_date < start_date:
        raise SystemExit("--end must be >= --start")
    if args.batch_days < 1 or args.max_days < 1:
        raise SystemExit("--batch-days and --max-days must be positive")

    requested = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    conn = get_db_connection()
    try:
        symbols = choose_symbols(conn, start_date, end_date, requested, args.max_symbols)
        if not symbols:
            raise SystemExit("No symbols found for selected period.")
        bars, by_date = load_daily_bars(conn, symbols, start_date, end_date, args.lookback_days)
        day_payloads, valid_dates = build_day_payloads(symbols, bars, by_date, start_date, end_date, args.lookback_days, args.max_days)
        if not day_payloads:
            raise SystemExit("No valid day payloads. Need at least 5 prior daily bars per symbol/date.")
        run_id = create_run(conn, args, symbols, status="running" if args.execute_ai else "dry_run")
        final_equity, equity_curve, ai_calls, summary = simulate(args, symbols, by_date, day_payloads, conn, run_id)
        return_pct = ((final_equity / args.initial_capital) - 1) * 100
        print(json.dumps({
            "status": "ok",
            "run_id": run_id,
            "execute_ai": args.execute_ai,
            "start": valid_dates[0].isoformat(),
            "end": valid_dates[-1].isoformat(),
            "symbols": symbols,
            "days": len(day_payloads),
            "ai_calls": ai_calls,
            "final_equity": round(final_equity, 2),
            "return_pct": round(return_pct, 3),
            "summary": summary,
        }, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
