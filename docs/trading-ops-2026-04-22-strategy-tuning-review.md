# Trading Ops: Strategy Reports Review And Tuning Plan

Date: 2026-04-22
Reviewed files:

- `ALGORITHMIC_STRATEGY_REPORT.md`
- `AUDIT_GENERAL_REPORT.md`
- `STRATEGIC_BOOST_DIRECTIONS.md`
- `audit_reports/*.md`

## Executive Summary

The reports are directionally useful, but some conclusions describe an older system state. The strongest still-relevant points are:

- reduce indicator/context noise;
- add market regime classification;
- add correlation/exposure controls;
- make execution more realistic;
- evolve trader DNA on longer windows with validation;
- use weighted consensus for Meta_Oracle;
- add source weighting/dedup/decay for sentiment.

The weakest or outdated points are:

- treating fallback hierarchy as an unconditional positive: unbounded fallback was one of the cost multipliers;
- claiming current ATR sizing as a live strength: current MOEX/crypto trader scripts use simple cash fraction sizing;
- treating `ai_backtester.py` as still making one AI call per historical candle/day: it has now been rebuilt as a guarded, batched, dry-run-by-default backtester;
- pushing async Gemini calls as a blanket fix: async is useful for market data collection, but dangerous for AI calls unless heavily rate-limited;
- prioritizing Windows portability over live trading correctness on this Linux server.

## Agreements

### Feature Pruning / Context Pruning

Agree strongly.

Both MOEX and crypto pipelines still calculate a broad indicator set. Keeping rich indicators in DB is acceptable, but sending all of them to AI is not. The correct optimization is not just deleting indicators globally; it is defining an agent-specific feature contract:

- VSA: volume ratio, spread, close location, VWAP distance, OBV/volume pressure;
- Chaos: Alligator state, fractals, momentum acceleration, ATR;
- PriceAction: candle body/range, levels, trend slope, breakout/retest flags;
- Quant: returns, volatility, z-score, correlation, regime, liquidity;
- Passive/Value: slower trend, drawdown, dividend/fundamental proxies if available.

### Market Regime Matrix

Agree strongly.

SMA50/breadth alone is too slow and too naive. The system needs a compact `analytics.market_regime` view/table with states such as:

- `trend_up`
- `trend_down`
- `range`
- `panic`
- `high_volatility`
- `illiquid`

The regime should use large-cap weighted breadth, index/large-cap movement, volatility, ADX/CHOP, volume expansion, and intraday dispersion.

### Correlation Filter

Agree strongly.

Current portfolio decisions can concentrate risk across correlated assets. This is a major drawdown risk. A correlation/exposure gate should be enforced outside the AI prompt, before execution:

- max correlated cluster exposure;
- max sector exposure;
- max single-name exposure;
- max total gross exposure per trader and per league.

### Weighted Consensus For Meta_Oracle

Agree, with a correction.

The weight should not be raw PnL. It should be rolling, risk-adjusted, and decayed:

- return;
- max drawdown;
- win rate;
- turnover;
- average holding time;
- recent model failure/timeout rate;
- risk violations.

Meta_Oracle should receive this compact table and only use agents with enough sample size.

### Backtester Risks

Agree historically, but current implementation has already been changed.

The previous concern was correct: per-day AI calls, no batching, no cost guard, lookahead risk, no commissions/slippage. The current `ai_backtester.py` now has:

- dry-run by default;
- explicit `--execute-ai`;
- explicit `--save`;
- daily batched decisions;
- hidden same-day close/high/low from the AI decision;
- commission and slippage parameters;
- result tables.

Remaining backtester work:

- add benchmark comparison;
- add short/margin model only after long-only is validated;
- add walk-forward/holdout evaluation;
- run tuning candidates through backtest before live promotion.

### Evolution Overfitting

Agree strongly.

Daily 24h evolution is too noisy for durable DNA changes. Evolution should not directly update live traits. It should create candidate changes, validate them, and promote only after backtest/forward-test.

## Partial Agreements

### Async Requests

Agree for data collection, not for AI decisions by default.

Async MOEX/Binance collection with bounded concurrency is useful. Async Gemini calls can quickly multiply requests and trigger quota/cost issues. AI should stay behind queue, lock, guard, and budgets.

### Volume Profile / POC

Agree in principle, but only if data supports it.

Real volume profile needs volume-by-price or tick/level data. With only OHLCV candles, POC can only be approximated. Initial implementation should use robust proxy levels:

- VWAP;
- previous day high/low/close;
- Donchian channel;
- high-volume candle levels;
- ATR bands.

### Sentiment Front-Running

Useful as a long-term vector, but risky as a near-term trading booster.

Entering within 10-30 seconds after news requires reliable low-latency feeds, deduplication, source ranking, and execution controls. Current sentiment script is better used first as a risk/regime input, not a front-running engine.

### Vector Memory

Agree, but retrieval must be narrow.

Vector memory should store compact, verified pattern cards, not long failed reports. Each memory item should include:

- market regime;
- setup features;
- action taken;
- result;
- confidence;
- expiration/decay metadata.

## Disagreements / Outdated Points

### Fallback Hierarchy As Pure Positive

Disagree.

Fallback is only positive when bounded. Without caps it multiplies cost and can exhaust subscription limits. The new guard/fallback caps are the correct operating model.

### Current ATR Sizing As A Confirmed Strength

Disagree for current live trader scripts.

The current `ai_paper_trader.py` and `ai_crypto_trader.py` use simple cash-fraction sizing. ATR/volatility sizing should be implemented in a shared risk module, not assumed to exist.

### Windows Portability As A Major Risk

Disagree on priority.

The production environment is Linux. Path cleanup is worthwhile, but trading correctness, cost control, risk limits, and execution realism are higher priority.

### Order Matching Uses Last Minute Close Exactly

Partly outdated.

Current `order_matching_engine.py` uses `analytics.trader_market_context_v.current_price`, not a direct `close` query in the matching code. The practical problem remains: no bid/ask, no slippage model, no liquidity cap, and weak cash/position validation.

## My Additional Thoughts

1. The next quality jump is not more AI. It is deterministic guardrails around AI.

The AI should propose actions, but a deterministic risk/execution layer must decide what can actually be placed.

2. The prompt should contain fewer indicators and more derived trading facts.

Examples:

- `trend_state=up/range/panic`;
- `price_vs_vwap_pct`;
- `volume_expansion_ratio`;
- `atr_pct`;
- `correlation_cluster`;
- `liquidity_bucket`;
- `distance_to_level_pct`.

3. Tuning should be promoted like code.

No direct nightly mutation of live traits. Use candidate table, validation, backtest, review, promotion.

4. Crypto should stay paused until the shared MOEX architecture is stable.

Crypto adds 24/7 scheduling, external exchange risk, faster decay, and API instability. Re-enable it after MOEX risk/execution controls are stable.

## Concrete Tuning Plan

### Phase 1: Measurement And Baselines

Goal: know what improves and what makes things worse.

Tasks:

- Add/confirm daily metrics view per trader:
  - equity curve;
  - realized/unrealized PnL;
  - max drawdown;
  - win rate;
  - turnover;
  - average action count;
  - AI failure rate from `trading.ai_call_log`.
- Add benchmark rows:
  - cash-only;
  - equal-weight top liquid names;
  - buy-and-hold selected symbols.
- Add a tuning score:
  - return adjusted by drawdown and turnover, not raw PnL.

Acceptance:

- one query/view can rank agents over 1d, 7d, 14d, 30d;
- Meta_Oracle can consume the compact ranking.

### Phase 2: Feature Contract And Prompt Pruning

Goal: reduce noise without reducing decision quality.

Tasks:

- Create a shared module `trading_feature_contract.py`.
- Define common compact fields:
  - price;
  - 5m/hour/day change;
  - ATR percent;
  - volume ratio;
  - trend state;
  - VWAP distance;
  - liquidity bucket;
  - correlation cluster;
  - key levels.
- Define per-agent feature subsets.
- Keep raw indicators in DB for research, but send only selected features to trader prompts.

Acceptance:

- typical MOEX trader prompt stays below 4k-6k chars;
- each agent sees strategy-relevant fields;
- no `MARKET: {}` and no huge raw indicator blobs.

### Phase 3: Deterministic Risk Engine

Goal: AI can suggest, but cannot create uncontrolled exposure.

Tasks:

- Add `risk_engine.py`.
- Enforce:
  - max position size per trade;
  - max single-symbol exposure;
  - max sector exposure;
  - max correlated cluster exposure;
  - max gross exposure;
  - cooldown after repeated losses;
  - action count limits per trader/session.
- Replace simple `cash * 0.1 / price` sizing with volatility/ATR-aware sizing.
- For shorts, add separate constraints before enabling real short logic.

Acceptance:

- every AI action is either accepted with normalized quantity or rejected with reason;
- journal/order records include risk decision metadata.

### Phase 4: Execution Realism

Goal: paper trading should punish unrealistic strategies.

Tasks:

- Update `order_matching_engine.py`:
  - cash check before buy;
  - position check before sell;
  - commission;
  - slippage;
  - liquidity cap as percent of recent volume;
  - stop-loss gap handling;
  - structured logs.
- Prefer limit execution at better of target/current only when market condition is realistic.

Acceptance:

- impossible buys cannot create negative cash;
- impossible sells cannot sell missing quantity;
- large orders get partially filled or rejected.

### Phase 5: Market Regime Layer

Goal: agents adapt activity to regime.

Tasks:

- Create `analytics.market_regime` refresh job.
- Inputs:
  - large-cap weighted breadth;
  - index or proxy basket return;
  - volatility/ATR;
  - ADX/CHOP;
  - volume expansion;
  - dispersion between leaders/laggards.
- Add regime to all trader prompts.
- Add regime-specific permission matrix:
  - scalpers active in high volatility but smaller size;
  - passive/value reduced during panic;
  - trend agents active in trend regimes;
  - mean reversion reduced during trend breakout.

Acceptance:

- every trader decision includes current regime;
- risk engine can reduce/increase max exposure by regime.

### Phase 6: Meta_Oracle Weighted Consensus

Goal: make ensemble smarter without adding many AI calls.

Tasks:

- Build `trading.trader_performance_v`.
- Add compact agent ranking to Meta_Oracle context.
- Weight agents by rolling risk-adjusted score.
- Penalize high turnover, drawdown, stale decisions, and AI failures.
- Add “enough sample size” rule.

Acceptance:

- Meta_Oracle prompt receives a concise table;
- weak/noisy agents have reduced influence.

### Phase 7: Evolution As Candidate Pipeline

Goal: avoid overfitting and prompt poisoning.

Tasks:

- Change evolution output from direct `learned_traits` update to candidate rows:
  - trader;
  - proposed trait;
  - evidence;
  - affected regime;
  - expiration;
  - confidence.
- Analyze 7-14 day windows, not just 24h.
- Validate:
  - max length;
  - banned instructions;
  - contradiction with base DNA;
  - backtest improvement;
  - no increase in drawdown beyond threshold.

Acceptance:

- no direct live DNA mutation;
- only validated candidates can be promoted.

### Phase 8: Sentiment As Risk Input First

Goal: use sentiment safely before attempting front-running.

Tasks:

- Add source weights.
- Deduplicate news.
- Add urgency decay.
- Compare news timestamp to price reaction.
- Store sentiment confidence and freshness.
- Feed only compact sentiment features to traders:
  - score;
  - freshness;
  - confidence;
  - source weight;
  - urgency.

Acceptance:

- stale sentiment cannot drive new trades;
- duplicated news does not amplify signal.

### Phase 9: Backtester-Gated Release Process

Goal: every tuning change proves itself before live use.

Tasks:

- Use `ai_backtester.py` for each candidate tuning.
- Add deterministic benchmark comparison.
- Add walk-forward split:
  - train/tune window;
  - validation window;
  - holdout window.
- Promote only if:
  - return improves;
  - drawdown does not worsen beyond threshold;
  - turnover does not explode;
  - AI calls stay within budget.

Acceptance:

- tuning changes have a backtest record;
- live promotion can be traced to a run id.

## Recommended Implementation Order

1. Metrics/performance views.
2. Feature contract and prompt pruning.
3. Risk engine.
4. Matching engine realism.
5. Market regime layer.
6. Meta_Oracle weighted consensus.
7. Evolution candidate pipeline.
8. Sentiment source weighting and freshness.
9. Backtester-gated promotion.

This order keeps decision quality stable: first measure, then reduce noise, then constrain risk, then add intelligence.
