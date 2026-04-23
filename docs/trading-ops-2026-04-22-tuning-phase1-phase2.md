# Trading Ops: Tuning Phase 1-2 Implementation

Date: 2026-04-22

Implemented now:

1. Metrics and baselines.
2. Feature contract and MOEX trader prompt pruning.

Postponed to evening:

3. Risk engine.
4. Matching engine realism.
5. Market regime layer.
6. Meta_Oracle weighted consensus.
7. Evolution candidate pipeline.
8. Sentiment as risk input.
9. Backtester-gated release process.
10. Deep AI input/output logging implementation from `/home/user/docs/trading-ops-2026-04-22-ai-logging-testing-plan.md`.

## Phase 1: Metrics And Baselines

Added `trading_metrics_setup.py`.

It creates or refreshes these views:

- `trading.current_prices_v`
- `trading.trader_position_value_v`
- `trading.trader_current_equity_v`
- `trading.trader_equity_daily_v`
- `trading.trader_equity_curve_v`
- `trading.trader_trade_outcomes_v`
- `trading.trader_trade_stats_v`
- `trading.trader_win_rate_v`
- `trading.trader_ai_failure_stats_v`
- `trading.trader_performance_v`
- `trading.benchmark_symbols_v`
- `trading.market_benchmark_v`

Purpose:

- current equity;
- cash/positions/gross exposure;
- approximate realized win rate from sell trades;
- turnover;
- AI failures from `trading.ai_call_log`;
- risk-adjusted `tuning_score`;
- cash baseline;
- equal-weight top-liquid benchmark;
- liquidity-weighted buy-and-hold benchmark.

Important limitation:

- `trading.daily_stats` is currently empty, so drawdown is `0` until daily equity snapshots start accumulating. Current equity is still available through `trading.trader_current_equity_v`.
- Win rate is approximate because old journal rows do not store explicit realized PnL. Sell rows are compared to weighted prior buys for the same trader/secid.

## Phase 2: Feature Contract

Added `trading_feature_contract.py`.

The module builds compact, agent-specific market features from `market_research_context.py`.

Common features:

- price;
- 5m/hour/day change;
- data age;
- trend state;
- issuer.

Agent-specific groups:

- VSA: volume ratios, spread, close location, body, levels.
- Chaos: Alligator/fractal-oriented fields, volatility.
- Elliott/PriceAction: trend, levels, candle structure.
- Contrarian: RSI/BB/VWAP reversion features.
- Quant: trend/momentum/volatility/liquidity fields.
- Passive/Value: slower weekly/month/year trend and liquidity.
- Meta_Oracle: compact common/flow/level/liquidity fields.

Updated `ai_paper_trader.py`:

- keeps `build_price_snapshot()` for execution price lookup;
- sends compact `MARKET_FEATURES` to AI instead of raw price-only `MARKET`;
- limits symbols through `AI_TRADER_MAX_SYMBOLS`, default 12;
- logs feature payload size;
- adds `AI_TRADER_DRY_RUN=1` to test without journal mutations.

Crypto feature contract is not yet wired. Crypto remains paused.

## Tests Added

Added:

- `tests/fake_gemini_cli.py`
- `tests/run_tuning_phase1_phase2_smoke.sh`

The smoke test checks:

1. Python compile.
2. Metrics views setup.
3. Metrics view row counts.
4. Feature contract shape and size.
5. MOEX trader dry-run with fake Gemini and no journal mutation.
6. Backtester dry-run.

## Test Results

Command:

```bash
/home/user/tests/run_tuning_phase1_phase2_smoke.sh
```

Result: passed.

Observed expected results:

- `trading.trader_current_equity_v`: 11 rows.
- `trading.trader_performance_v`: 11 rows.
- `trading.benchmark_symbols_v`: 21 rows.
- `trading.market_benchmark_v`: 5 rows.
- `Chaos_Bill` feature payload with 8 symbols: 1195 chars.
- `ai_paper_trader.py Chaos_Bill` dry-run:
  - fake Gemini response parsed;
  - valid action count: 1;
  - journal count before and after remained `7`.
- `ai_backtester.py` dry-run:
  - 3 prepared days;
  - 5 symbols;
  - `ai_calls=0`;
  - final equity unchanged.

Additional feature payload checks:

- VSA Victor, 8 symbols: 2128 chars.
- Chaos Bill, 8 symbols: 1195 chars.
- PriceAction Nikita, 8 symbols: 2371 chars.
- Quant Diana, 8 symbols: 1239 chars.
- Value Monya, 8 symbols: 1516 chars.
- Meta Oracle, 8 symbols: 2141 chars.

## Sample Diagnostic Queries

Trader ranking:

```sql
SELECT
    trader_name,
    round(total_equity, 2) AS total_equity,
    round(return_pct, 3) AS return_pct,
    round(max_drawdown_pct, 3) AS max_drawdown_pct,
    win_rate_pct,
    trade_count,
    round(turnover_to_equity, 3) AS turnover_to_equity,
    ai_attempts,
    ai_failures,
    round(tuning_score, 3) AS tuning_score
FROM trading.trader_performance_v
ORDER BY tuning_score DESC;
```

Benchmarks:

```sql
SELECT benchmark_name, lookback_days, round(return_pct, 3), symbols_count
FROM trading.market_benchmark_v
ORDER BY benchmark_name, lookback_days;
```

## Evening Backlog

Next implementation order:

1. `risk_engine.py`
   - max position size;
   - max gross exposure;
   - max sector/correlation exposure;
   - ATR/volatility sizing;
   - cooldown;
   - max actions per trader/session.

2. `order_matching_engine.py`
   - cash check;
   - position check;
   - commission;
   - slippage;
   - liquidity cap;
   - stop gap behavior.

3. `analytics.market_regime`
   - table/view;
   - refresh job;
   - prompt integration.

4. `Meta_Oracle`
   - consume `trading.trader_performance_v`;
   - weighted consensus by rolling risk-adjusted score.

5. Evolution candidates
   - no direct nightly mutation;
   - candidate table;
   - validation;
   - backtest/promotion.

6. Sentiment risk input
   - source weights;
   - dedup;
   - urgency decay;
   - freshness/confidence.

7. Backtester-gated release
   - benchmark comparison;
   - holdout;
   - promotion rule.

8. Deep AI I/O logging implementation
   - implement `ai_io_debug_logger.py`;
   - add `input_meta` to Gemini runner;
   - caller metadata;
   - one-command AI smoke suite.
