# Trading Ops: AI Cost Controls And Backtester Audit

Date: 2026-04-22
Scope: MOEX/crypto AI scripts, Gemini CLI usage, postmarket scripts, `ai_backtester.py`.

## Current Runtime State

- MOEX traders are still paused in crontab:
  - `run_ai_job_dispatcher.sh` is commented out.
  - `run_matching_engine_once.sh` is commented out.
- Crypto AI remains paused in crontab.
- No active trader/Gemini worker processes were found during the final check.

## Implemented Cost Controls

1. Central AI guard:
   - Added `ai_cost_guard.py`.
   - Creates `trading.ai_call_log`.
   - Logs every allowed, blocked, skipped, failed, timed-out, exhausted, parse-failed, and successful AI attempt.
   - Adds per-category prompt limits, hourly request budgets, fallback limits, and model health checks.

2. Gemini runner integration:
   - `gemini_cli_runner.py` now calls the guard before running Gemini.
   - Real model attempts are capped by category.
   - Recently failing models can be skipped before a request is spent.
   - All callers can pass `category` and `trader_name`.

3. Model order:
   - `ai_model_rank.json` now starts with Flash-class models.
   - Pro/preview model remains available only as late fallback instead of default first request.

4. MOEX context bug:
   - `market_research_context.py` now includes `engine`.
   - MOEX trader filtering by `engine == 'stock'` now works; before this, `MARKET` could be `{}`.

5. Trader scripts:
   - `ai_paper_trader.py` and `ai_crypto_trader.py` use Flash-first model lists.
   - KB context is cached through `ai_context_cache.py`.
   - Low-quality KB responses such as `KB offline`, `No context found`, and failed-analysis markers are not injected into prompts.
   - Empty market snapshots now fail fast before spending AI calls.

6. Dispatcher:
   - `ai_job_dispatcher.py` now has:
     - full MOEX wave interval: default 30 minutes,
     - event wave interval: default 5 minutes,
     - per-trader TTL: default 20 minutes,
     - event trigger thresholds for 5-minute and 1-hour market moves,
     - crypto TTL if crypto is later re-enabled.
   - `run_ai_job_dispatcher.sh` exports these defaults explicitly.

7. Sentiment:
   - `ai_sentiment_oracle.py` now batches all due tickers into one AI call.
   - Freshness check skips tickers updated within the configured interval.
   - It no longer asks Gemini to browse/find latest news from inside a no-tools prompt.

8. Daily report:
   - `ai_daily_report.py` now batches per-trader lessons into one league audit call.
   - Staff recommendations still use a separate call.
   - Existing quality gate remains; failed/empty lessons prevent Telegram and ALGO KB upload.
   - `ai_crypto_daily_report.py` now also batches crypto trader lessons into one call and skips low-quality per-trader KB uploads. Crypto remains paused in crontab.

9. Evolution/incubator/watchdog:
   - `ai_evolution.py` aggregates market data instead of sending raw windows.
   - `ai_genetic_incubator.py` aggregates weekly data and trims indicators.
   - `ai_watchdog_analyzer.py` uses guard/category and skips low-quality KB uploads.
   - Evolution prompt size measured after compression: about 42.6k chars, below the 60k guard limit.
   - Incubator prompt size measured after compression: about 6.2k chars.

10. Wrappers:
   - `run_postmarket_ai_job.sh` exports guard/fallback defaults for nightly scripts.
   - `run_ai_trader_once.sh` exports trader guard defaults and KB cache TTL.

## `ai_backtester.py` Audit

### Why It Was Disabled

Before this change, the working file was effectively a stub. The repository diff also shows an older implementation that was not safe to run regularly:

- It called Gemini once per historical trading day.
- It used a loose CLI call path instead of the centralized guarded runner.
- It had no prompt budget, no request budget, no fallback cap, and no model health circuit breaker.
- It used `--approval-mode yolo`.
- It did not batch historical decisions.
- It did not clearly prevent lookahead bias.
- It did not model commission/slippage.
- It did not persist normalized run/trade results in a dedicated schema.
- It used `analytics.trader_market_windows` snapshots, which are rolling windows, not a clean daily historical backtest source.

Conclusion: it was right to keep it disabled until it had guardrails. A per-day AI backtester could burn limits very quickly, especially if combined with fallback loops.

### New Backtester Behavior

`ai_backtester.py` has been rebuilt as a safe batched daily backtester:

- Default mode is dry-run. It validates data and prompt size without calling Gemini.
- Real AI calls require explicit `--execute-ai`.
- DB writes require explicit `--save`.
- Data source is `raw.candle` with `engine='stock'` and `interval_name='1d'`.
- Each target day only receives features available before that date plus tradable target open.
- It batches days into one AI call per `--batch-days`.
- It supports symbol caps, day caps, lookback caps, commission bps, slippage bps, and position fraction.
- It writes optional results to:
  - `trading.ai_backtest_runs`
  - `trading.ai_backtest_trades`
- Current simulation is long-only: `buy`, `sell`, `hold`.

### Known Limitations

- No margin/short/cover simulation yet.
- Daily bars only; no intraday execution model.
- It backtests a compact strategy prompt, not the full live trader prompt with portfolio/KB/DNA history.
- It needs a comparison layer against buy-and-hold and deterministic baselines before cron scheduling.

## Backtester Launch Plan

1. Dry-run data validation:

```bash
/home/user/trading_venv/bin/python /home/user/ai_backtester.py \
  --start 2026-04-15 --end 2026-04-21 \
  --trader Chaos_Bill \
  --max-days 3 --max-symbols 5 --batch-days 2
```

2. First real AI smoke, no DB save:

```bash
/home/user/trading_venv/bin/python /home/user/ai_backtester.py \
  --start 2026-04-15 --end 2026-04-17 \
  --trader Chaos_Bill \
  --max-days 3 --max-symbols 5 --batch-days 3 \
  --execute-ai
```

3. First saved run after smoke succeeds:

```bash
/home/user/trading_venv/bin/python /home/user/ai_backtester.py \
  --start 2026-04-01 --end 2026-04-21 \
  --trader Chaos_Bill \
  --max-days 10 --max-symbols 8 --batch-days 5 \
  --execute-ai --save
```

4. Expand only after comparing results:
   - Compare return/drawdown against buy-and-hold for selected symbols.
   - Review `trading.ai_call_log` for request count and failures.
   - Review `trading.ai_backtest_trades` for nonsensical turnover.

5. Cron only after manual validation:
   - Suggested cadence: weekly weekend run.
   - Keep `--max-days` and `--batch-days` bounded.
   - Use `flock` and guard defaults.

## Tests Run

- Python compile:
  - `ai_cost_guard.py`
  - `ai_context_cache.py`
  - `gemini_cli_runner.py`
  - `market_research_context.py`
  - `ai_paper_trader.py`
  - `ai_crypto_trader.py`
  - `ai_job_dispatcher.py`
  - `ai_sentiment_oracle.py`
  - `ai_daily_report.py`
  - `ai_evolution.py`
  - `ai_genetic_incubator.py`
  - `ai_watchdog_analyzer.py`
  - `ai_crypto_daily_report.py`
  - `ai_macro_sensei.py`
  - `ai_call_fix.py`
  - `ai_backtester.py`
- Shell syntax:
  - `run_ai_job_dispatcher.sh`
  - `run_ai_trader_once.sh`
  - `run_postmarket_ai_job.sh`
  - nightly wrappers.
- `git diff --check`: clean for touched files.
- Guard schema creation: OK.
- Context cache schema creation: OK.
- MOEX context check: 27 total context rows, engines `currency`, `futures`, `stock`; 23 stock rows, 21 stock snapshot rows.
- Guard budget-block smoke: OK.
- Guard fallback cap smoke: OK.
- Guard model-health skip smoke: OK.
- Sentiment dry-run: OK, one batch for 3 tickers.
- Daily report with AI blocked: quality gate correctly skipped Telegram and ALGO KB upload.
- Evolution/incubator/watchdog with AI blocked in test mode: no KB upload.
- Backtester dry-run: OK, 3 days, 5 symbols, 0 AI calls.
- Backtester execute path with fake Gemini CLI: OK, 1 AI call, one simulated SBER buy, equity calculated.

## Operational Notes

- The test fake Gemini call inserted a successful `backtest` row into `trading.ai_call_log` because it exercised the real guarded runner path with a fake binary.
- Budget-block test rows were also inserted into `trading.ai_call_log`.
- These are useful for verifying logging and can be filtered by recent timestamps/status if needed.
