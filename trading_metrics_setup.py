#!/usr/bin/env python3
from __future__ import annotations

import os

import psycopg2


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "market_research"),
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

DDL = """
CREATE SCHEMA IF NOT EXISTS trading;

CREATE OR REPLACE VIEW trading.current_prices_v AS
SELECT
    secid,
    engine,
    market,
    board,
    current_price::numeric AS price,
    updated_at
FROM analytics.trader_market_context_v
WHERE current_price IS NOT NULL;

CREATE OR REPLACE VIEW trading.trader_position_value_v AS
SELECT
    p.trader_name,
    p.secid,
    p.quantity,
    p.avg_entry_price,
    cp.price AS current_price,
    (p.quantity * COALESCE(cp.price, p.avg_entry_price))::numeric AS position_value,
    (p.quantity * (COALESCE(cp.price, p.avg_entry_price) - p.avg_entry_price))::numeric AS unrealized_pnl,
    CASE
        WHEN p.avg_entry_price > 0
        THEN ((COALESCE(cp.price, p.avg_entry_price) / p.avg_entry_price) - 1) * 100
        ELSE 0
    END::numeric AS unrealized_pnl_pct,
    cp.updated_at AS price_updated_at
FROM trading.position p
LEFT JOIN trading.current_prices_v cp
    ON cp.secid = p.secid
   AND cp.engine = 'stock'
WHERE p.quantity <> 0;

CREATE OR REPLACE VIEW trading.trader_current_equity_v AS
SELECT
    pf.trader_name,
    pf.cash_balance::numeric AS cash_balance,
    COALESCE(sum(pv.position_value), 0)::numeric AS positions_value,
    (pf.cash_balance + COALESCE(sum(pv.position_value), 0))::numeric AS total_equity,
    COALESCE(sum(abs(pv.position_value)), 0)::numeric AS gross_exposure,
    CASE
        WHEN (pf.cash_balance + COALESCE(sum(pv.position_value), 0)) > 0
        THEN COALESCE(sum(abs(pv.position_value)), 0) / (pf.cash_balance + COALESCE(sum(pv.position_value), 0)) * 100
        ELSE 0
    END::numeric AS gross_exposure_pct,
    count(pv.secid)::integer AS open_positions,
    max(pv.price_updated_at) AS prices_updated_at,
    pf.updated_at AS portfolio_updated_at
FROM trading.portfolio pf
LEFT JOIN trading.trader_position_value_v pv
    ON pv.trader_name = pf.trader_name
GROUP BY pf.trader_name, pf.cash_balance, pf.updated_at;

CREATE OR REPLACE VIEW trading.trader_equity_daily_v AS
SELECT
    trader_name,
    stat_date,
    total_value::numeric AS total_equity,
    cash_balance::numeric AS cash_balance,
    positions_value::numeric AS positions_value,
    created_at,
    'daily_stats'::text AS source
FROM trading.daily_stats
UNION ALL
SELECT
    trader_name,
    current_date AS stat_date,
    total_equity,
    cash_balance,
    positions_value,
    now() AS created_at,
    'current_equity'::text AS source
FROM trading.trader_current_equity_v c
WHERE NOT EXISTS (
    SELECT 1
    FROM trading.daily_stats d
    WHERE d.trader_name = c.trader_name
      AND d.stat_date = current_date
);

CREATE OR REPLACE VIEW trading.trader_equity_curve_v AS
SELECT
    trader_name,
    stat_date,
    total_equity,
    cash_balance,
    positions_value,
    source,
    lag(total_equity) OVER (PARTITION BY trader_name ORDER BY stat_date) AS previous_equity,
    CASE
        WHEN lag(total_equity) OVER (PARTITION BY trader_name ORDER BY stat_date) > 0
        THEN ((total_equity / lag(total_equity) OVER (PARTITION BY trader_name ORDER BY stat_date)) - 1) * 100
        ELSE NULL
    END::numeric AS daily_return_pct,
    max(total_equity) OVER (
        PARTITION BY trader_name
        ORDER BY stat_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS peak_equity,
    CASE
        WHEN max(total_equity) OVER (
            PARTITION BY trader_name
            ORDER BY stat_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) > 0
        THEN ((total_equity / max(total_equity) OVER (
            PARTITION BY trader_name
            ORDER BY stat_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )) - 1) * 100
        ELSE 0
    END::numeric AS drawdown_pct
FROM trading.trader_equity_daily_v;

CREATE OR REPLACE VIEW trading.trader_trade_outcomes_v AS
SELECT
    j.id,
    j.trader_name,
    j.secid,
    upper(j.action) AS action,
    j.quantity,
    j.price,
    j.created_at,
    prior.avg_prior_buy_price,
    CASE
        WHEN prior.avg_prior_buy_price > 0
        THEN (j.price - prior.avg_prior_buy_price) * j.quantity
        ELSE NULL
    END::numeric AS approx_realized_pnl,
    CASE
        WHEN prior.avg_prior_buy_price > 0
        THEN j.price > prior.avg_prior_buy_price
        ELSE NULL
    END AS is_win
FROM trading.journal j
LEFT JOIN LATERAL (
    SELECT
        sum(b.quantity * b.price) / NULLIF(sum(b.quantity), 0) AS avg_prior_buy_price
    FROM trading.journal b
    WHERE b.trader_name = j.trader_name
      AND b.secid = j.secid
      AND upper(b.action) IN ('BUY', 'COVER')
      AND b.created_at < j.created_at
) prior ON true
WHERE upper(j.action) IN ('SELL', 'SHORT');

CREATE OR REPLACE VIEW trading.trader_trade_stats_v AS
SELECT
    trader_name,
    count(*)::integer AS trade_count,
    count(*) FILTER (WHERE upper(action) = 'BUY')::integer AS buy_count,
    count(*) FILTER (WHERE upper(action) = 'SELL')::integer AS sell_count,
    count(*) FILTER (WHERE upper(action) = 'SHORT')::integer AS short_count,
    count(*) FILTER (WHERE upper(action) = 'COVER')::integer AS cover_count,
    COALESCE(sum(abs(quantity * price)), 0)::numeric AS turnover_value,
    min(created_at) AS first_trade_at,
    max(created_at) AS last_trade_at
FROM trading.journal
GROUP BY trader_name;

CREATE OR REPLACE VIEW trading.trader_win_rate_v AS
SELECT
    trader_name,
    count(*) FILTER (WHERE is_win IS NOT NULL)::integer AS evaluated_exits,
    count(*) FILTER (WHERE is_win IS TRUE)::integer AS winning_exits,
    count(*) FILTER (WHERE is_win IS FALSE)::integer AS losing_exits,
    CASE
        WHEN count(*) FILTER (WHERE is_win IS NOT NULL) > 0
        THEN count(*) FILTER (WHERE is_win IS TRUE)::numeric / count(*) FILTER (WHERE is_win IS NOT NULL) * 100
        ELSE NULL
    END::numeric AS win_rate_pct,
    COALESCE(sum(approx_realized_pnl), 0)::numeric AS approx_realized_pnl
FROM trading.trader_trade_outcomes_v
GROUP BY trader_name;

CREATE OR REPLACE VIEW trading.trader_ai_failure_stats_v AS
SELECT
    COALESCE(trader_name, call_name) AS trader_name,
    count(*)::integer AS ai_attempts,
    count(*) FILTER (WHERE status = 'success')::integer AS ai_successes,
    count(*) FILTER (WHERE status IN ('exhausted', 'timeout', 'error', 'parse_error', 'budget_blocked'))::integer AS ai_failures,
    count(*) FILTER (WHERE status = 'budget_blocked')::integer AS ai_budget_blocks,
    CASE
        WHEN count(*) > 0
        THEN count(*) FILTER (WHERE status IN ('exhausted', 'timeout', 'error', 'parse_error', 'budget_blocked'))::numeric / count(*) * 100
        ELSE 0
    END::numeric AS ai_failure_rate_pct,
    avg(prompt_chars)::numeric AS avg_prompt_chars,
    max(created_at) AS last_ai_call_at
FROM trading.ai_call_log
WHERE category = 'trader'
GROUP BY COALESCE(trader_name, call_name);

CREATE OR REPLACE VIEW trading.trader_performance_v AS
WITH curve AS (
    SELECT
        trader_name,
        min(drawdown_pct)::numeric AS max_drawdown_pct,
        count(*)::integer AS equity_points
    FROM trading.trader_equity_curve_v
    GROUP BY trader_name
),
initial_capital AS (
    SELECT
        p.trader_name,
        COALESCE(
            (SELECT d.total_value::numeric
             FROM trading.daily_stats d
             WHERE d.trader_name = p.trader_name
             ORDER BY d.stat_date ASC
             LIMIT 1),
            10000::numeric
        ) AS initial_capital
    FROM trading.portfolio p
)
SELECT
    e.trader_name,
    ic.initial_capital,
    e.cash_balance,
    e.positions_value,
    e.total_equity,
    e.gross_exposure,
    e.gross_exposure_pct,
    e.open_positions,
    CASE
        WHEN ic.initial_capital > 0
        THEN ((e.total_equity / ic.initial_capital) - 1) * 100
        ELSE 0
    END::numeric AS return_pct,
    COALESCE(c.max_drawdown_pct, 0)::numeric AS max_drawdown_pct,
    COALESCE(w.win_rate_pct, NULL)::numeric AS win_rate_pct,
    COALESCE(w.evaluated_exits, 0)::integer AS evaluated_exits,
    COALESCE(w.approx_realized_pnl, 0)::numeric AS approx_realized_pnl,
    COALESCE(t.trade_count, 0)::integer AS trade_count,
    COALESCE(t.turnover_value, 0)::numeric AS turnover_value,
    CASE
        WHEN e.total_equity > 0
        THEN COALESCE(t.turnover_value, 0) / e.total_equity
        ELSE 0
    END::numeric AS turnover_to_equity,
    COALESCE(ai.ai_attempts, 0)::integer AS ai_attempts,
    COALESCE(ai.ai_failures, 0)::integer AS ai_failures,
    COALESCE(ai.ai_failure_rate_pct, 0)::numeric AS ai_failure_rate_pct,
    (
        CASE
            WHEN ic.initial_capital > 0
            THEN ((e.total_equity / ic.initial_capital) - 1) * 100
            ELSE 0
        END
        + COALESCE(c.max_drawdown_pct, 0) * 0.70
        - LEAST(COALESCE(t.turnover_value, 0) / NULLIF(e.total_equity, 0), 20) * 0.10
        - COALESCE(ai.ai_failure_rate_pct, 0) * 0.05
    )::numeric AS tuning_score,
    e.prices_updated_at,
    t.first_trade_at,
    t.last_trade_at,
    ai.last_ai_call_at
FROM trading.trader_current_equity_v e
JOIN initial_capital ic
    ON ic.trader_name = e.trader_name
LEFT JOIN curve c
    ON c.trader_name = e.trader_name
LEFT JOIN trading.trader_trade_stats_v t
    ON t.trader_name = e.trader_name
LEFT JOIN trading.trader_win_rate_v w
    ON w.trader_name = e.trader_name
LEFT JOIN trading.trader_ai_failure_stats_v ai
    ON ai.trader_name = e.trader_name;

CREATE OR REPLACE VIEW trading.benchmark_symbols_v AS
SELECT
    secid,
    avg(value)::numeric AS avg_daily_value,
    count(*)::integer AS daily_bars,
    row_number() OVER (ORDER BY avg(value) DESC NULLS LAST, secid ASC)::integer AS liquidity_rank
FROM raw.candle
WHERE engine = 'stock'
  AND interval_name = '1d'
  AND candle_time::date >= current_date - interval '120 days'
GROUP BY secid
HAVING count(*) >= 10;

CREATE OR REPLACE VIEW trading.market_benchmark_v AS
WITH lookbacks(days) AS (
    VALUES (7), (30)
),
symbols AS (
    SELECT secid, avg_daily_value
    FROM trading.benchmark_symbols_v
    WHERE liquidity_rank <= 10
),
priced AS (
    SELECT
        l.days,
        s.secid,
        s.avg_daily_value,
        (
            SELECT close::numeric
            FROM raw.candle c
            WHERE c.engine = 'stock'
              AND c.interval_name = '1d'
              AND c.secid = s.secid
              AND c.candle_time::date <= current_date - l.days
            ORDER BY c.candle_time DESC
            LIMIT 1
        ) AS start_close,
        (
            SELECT close::numeric
            FROM raw.candle c
            WHERE c.engine = 'stock'
              AND c.interval_name = '1d'
              AND c.secid = s.secid
              AND c.candle_time::date <= current_date
            ORDER BY c.candle_time DESC
            LIMIT 1
        ) AS end_close
    FROM lookbacks l
    CROSS JOIN symbols s
),
symbol_returns AS (
    SELECT
        days,
        secid,
        avg_daily_value,
        CASE
            WHEN start_close > 0 AND end_close IS NOT NULL
            THEN ((end_close / start_close) - 1) * 100
            ELSE NULL
        END::numeric AS return_pct
    FROM priced
)
SELECT
    'cash'::text AS benchmark_name,
    0::integer AS lookback_days,
    0::numeric AS return_pct,
    0::integer AS symbols_count,
    now() AS calculated_at
UNION ALL
SELECT
    'equal_weight_top_liquid'::text AS benchmark_name,
    days AS lookback_days,
    avg(return_pct)::numeric AS return_pct,
    count(return_pct)::integer AS symbols_count,
    now() AS calculated_at
FROM symbol_returns
GROUP BY days
UNION ALL
SELECT
    'liquidity_weighted_buy_hold'::text AS benchmark_name,
    days AS lookback_days,
    (sum(return_pct * avg_daily_value) / NULLIF(sum(avg_daily_value), 0))::numeric AS return_pct,
    count(return_pct)::integer AS symbols_count,
    now() AS calculated_at
FROM symbol_returns
GROUP BY days;
"""


def main() -> int:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        with conn.cursor() as cur:
            checks = {
                "trader_current_equity_v": "SELECT count(*) FROM trading.trader_current_equity_v",
                "trader_performance_v": "SELECT count(*) FROM trading.trader_performance_v",
                "benchmark_symbols_v": "SELECT count(*) FROM trading.benchmark_symbols_v",
                "market_benchmark_v": "SELECT count(*) FROM trading.market_benchmark_v",
            }
            for name, sql in checks.items():
                cur.execute(sql)
                print(f"{name}: {cur.fetchone()[0]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
