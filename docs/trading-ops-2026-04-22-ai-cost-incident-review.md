# Trading Ops: AI Cost Incident Review 2026-04-22

## Executive Summary

The catastrophic Gemini Ultra consumption is primarily a request-volume problem, then a token-size problem.

Main drivers:

1. The AI trader queue can generate up to 132 trader jobs per hour per market: 11 traders * one full wave every 5 minutes.
2. Each trader job can call more than one Gemini model because the fallback chain starts with `gemini-3.1-pro-preview`, which the logs show frequently returns `exhausted` before the script falls back to Flash.
3. Failed jobs are especially expensive: they often wait through one or more long Gemini attempts and then still produce no decision.
4. Nightly scripts send very large prompts: `ai_evolution.py` builds about 208K chars today; `ai_genetic_incubator.py` builds about 194K chars.
5. `ai_daily_report.py` calls Gemini once per trader plus staff recommendations. With 11 traders and fallback, one report can fan out into many requests.
6. `ai_sentiment_oracle.py` calls Gemini once per ticker, every scheduled run, without real news payload. This is high request volume with weak decision value.

Current protection status:

- Traders are paused in cron as of 2026-04-22.
- Crypto cron is already paused.
- Postmarket AI jobs now have `flock` and timeout wrappers.
- Bad KB writes are now guarded, but that does not solve request volume by itself.

## Evidence

### Current Cron

At the time of review:

- `run_ai_job_dispatcher.sh` is disabled by `DISABLED 2026-04-22 trader pause`.
- `run_matching_engine_once.sh` is disabled by the same pause.
- Crypto cron remains disabled.
- `ai_sentiment_oracle.py` is still scheduled hourly from 09:00 to 23:00 on weekdays.
- Postmarket AI scripts are scheduled at 00:05, 00:30, 00:45, and 01:00.

### AI Jobs In Last 24 Hours

From `trading.ai_jobs`:

- Total trader jobs: 869.
- Crypto trader jobs: 583 total, 503 succeeded, 80 failed.
- MOEX trader jobs: 286 total, 190 succeeded, 90 failed, 6 skipped by pause.

Hourly peaks:

- Crypto reached 132 trader jobs/hour for several hours.
- MOEX reached 132 trader jobs/hour at 10:00 MSK.

This matches the formula from `PROMPT_DEBUG_COSTS.md`:

`traders * frequency * prompt_size`

For one market:

`11 traders * 12 waves/hour = 132 trader prompts/hour`

For MOEX + crypto together, if both are enabled:

`132 + 132 = 264 trader prompts/hour`, before fallback multiplication.

### Fallback Multiplication

Log evidence:

- `ai_trader.log`: 847 `Decision`, 367 `AI Failed`, 2735 `exhausted`, 91 `timed out`.
- `ai_crypto_trader.log`: 509 `Decision`, 99 `AI Failed`, 563 `exhausted`, 94 `timed out`.
- Recent crypto decisions usually show `gemini-3.1-pro-preview exhausted` immediately before a successful `gemini-3-flash-preview` decision.

This means a nominal "one trader decision" is often at least two Gemini requests:

1. Pro preview attempt.
2. Flash fallback attempt.

When Flash times out or parsing fails, the job can consume even more wall time and still fail.

### Prompt Sizes

Measured locally without making Gemini calls:

- MOEX current price snapshot: 24 assets, 1,379 JSON chars.
- MOEX compact full context: 103,455 JSON chars.
- Crypto current price snapshot: 5 assets, 299 JSON chars.
- Crypto compact full context: 6,777 JSON chars.
- Evolution market data prompt payload: about 208,064 chars.
- Incubator weekly payload: about 194,341 chars.
- Watchdog analyzer final prompt: about 7,102 chars after summarization, although raw log tails total about 1,996,890 chars.

Important: `compact_context_payload()` is not used by the live trader prompts today. That is good for token cost, but it also means the system has no central context budget mechanism if future code starts using compact full context directly.

### MOEX Market Context Bug

`ai_paper_trader.py` filters:

`payload.get('engine') == 'stock'`

But `market_research_context.py` does not include the `engine` field in returned payloads. Result:

- `stock_context` becomes empty.
- `snaps` becomes `{}`.
- live trader prompts show `MARKET: {}`.

This is not the main token-cost cause because it actually reduces prompt size. It is a quality bug: the system spends Gemini requests while withholding market data from the model.

## Root Causes

### Critical 1: Trader Wave Frequency Is Too High

`ai_job_dispatcher.py` queues all 11 MOEX traders every 5 minutes when no pending trader jobs exist.

`run_ai_job_dispatcher.sh` runs every minute and internally ticks three times, 25 seconds apart. This does not enqueue every tick, but it aggressively drains the queue and starts jobs almost continuously.

Impact:

- high request volume even when the market has not materially changed;
- repeated AI decisions on near-identical context;
- failed/slow jobs do not stop the next wave once queue drains.

### Critical 2: Model Rank Starts With A Bad/Expensive Model For Frequent Trading

`ai_model_rank.json` gives priority 1 to `gemini-3.1-pro-preview`.

Logs show it is frequently exhausted. The system retries it for every trader job instead of cooling it down globally.

Impact:

- one wasted request per trader decision in many cases;
- Pro attempts add latency and can cascade into timeouts;
- no global health/circuit breaker prevents repeated failure.

### Critical 3: Fallback Has No Budget Guard

`gemini_cli_runner.py` can iterate across the model rank for each call. This is useful for availability, but dangerous without per-call and per-hour budgets.

Impact:

- request count can multiply silently;
- a bad model state affects every script independently;
- logs show thousands of exhausted fallback events.

### Critical 4: Failed Jobs Are Expensive And Repeated

In the last 24 hours:

- MOEX had 90 failed trader jobs with average duration about 135 seconds.
- Crypto had 80 failed trader jobs with average duration about 132 seconds.

These failures still consume requests and lock slots, but produce no trading value.

### Major 1: Per-Trader KB Query Is Repeated Too Often

Every `ai_paper_trader.py` and `ai_crypto_trader.py` call queries ALGO KB per trader:

- `Strategic Alpha for [...] Lessons for <trader>. Risk Level.`
- `Patterns for [...] Lessons for <trader>. Risk Level.`

The query often returns "not enough information". It is both low value and repeated at high frequency.

If the LightRAG query path uses LLM generation, this can also consume AI resources indirectly. Even if it is local, it adds latency and low-quality context.

### Major 2: Sentiment Oracle Is A Request Multiplier With Weak Input

`ai_sentiment_oracle.py` loops over 10 tickers and calls Gemini for each ticker. It does this from cron hourly during the trading day.

The `fetch_rss_news()` function does not fetch actual RSS; it returns an instruction asking AI to find current news from its own knowledge. With CLI tools disabled, the model cannot really browse.

Impact:

- up to 150 ticker-level sentiment requests per weekday;
- high hallucination risk;
- weak value for trading decisions.

### Major 3: Daily Reports Fan Out Per Trader

`ai_daily_report.py` calls Gemini for each trader, then calls Gemini again for staff suggestions.

Impact:

- 12 logical AI calls for 11 traders before fallback;
- the report can stall on repeated Pro timeouts;
- the same alpha/tech context is duplicated into each trader prompt.

### Major 4: Evolution And Incubator Send Huge Payloads

`ai_evolution.py` sends a 24-hour multi-asset market dataset and all trades in one prompt.

`ai_genetic_incubator.py` sends seven days of market windows with indicators.

Impact:

- 190K-210K char prompts in the current system;
- high cost per request;
- quality risk from noisy indicators and overfitting.

### Major 5: Watchdog Analyzer Is Mostly Safe Now, But Needs Bounds

`ai_watchdog_analyzer.py` summarizes logs before sending to Gemini. Current prompt is around 7K chars, which is reasonable.

Risk:

- if regex captures larger error samples later, prompt size can grow;
- it should still have a hard prompt budget and deterministic pre-analysis.

### Major 6: Crypto Was Previously 24/7 And Would Overlap With MOEX

Crypto is paused now, but the queue data shows it produced 583 trader jobs in the last 24 hours before pause.

If re-enabled with the same pattern, it will consume requests continuously and can overlap with MOEX hours.

## Comparison With PROMPT_DEBUG_COSTS.md

### Agree

I agree with the core formula:

`Количество трейдеров * Частота запуска * Средний размер промпта`

The DB proves the frequency part: up to 132 trader jobs/hour per market.

I agree that `ai_crypto_trader.py`, `ai_paper_trader.py`, and `ai_evolution.py` are the right priority files.

I agree that `ai_model_rank.json` is a major cause. The first model is not a neutral ordering choice; it causes repeated wasted Pro attempts.

I agree that prompt length logging is mandatory. Right now we are investigating from logs and inferred sizes; the runner should log every call centrally.

I agree that `compact_context_payload()` and NaN/None pruning need attention. Full compact MOEX context is about 103K chars today, so using it naively would be expensive.

I agree with checking DB activity. The `trading.ai_jobs` table was more useful than `trading.journal` for this incident because failed AI calls often produce no journal rows.

### Partially Agree

`load_market_context()` returning too many assets is a future risk more than the current MOEX trader prompt reality. Today MOEX trader prompt accidentally sends `MARKET: {}` because of the `engine` bug. Crypto sends only 5 assets.

`ai_backtester.py` is not currently the live cause. In this working tree it is a stub and is not scheduled. The warning is still valid for future weekend stress tests: a real backtester that calls AI per candle would be catastrophic.

### Disagree Or Reframe

The biggest current issue is not prompt size in live trader calls. It is request count plus fallback multiplication. Live trader prompts are not huge today, but they are extremely frequent.

The hidden-loop issue is not a literal `while true` inside the traders anymore. It is an architectural loop: cron every minute -> dispatcher ticks three times -> waves every five minutes -> 11 agents -> fallback retries.

### New Ideas Triggered By The File

The file pushed the audit toward quantitative measurement. That exposed:

1. `MARKET: {}` in MOEX prompts due missing `engine`.
2. The 103K char risk of full compact MOEX context.
3. The 208K/194K nightly prompt sizes.
4. The need for central prompt/request accounting in `gemini_cli_runner.py`, not scattered debug prints.

## Fix Plan Without Hurting Decision Quality

Principle: do not simply "call AI less". Call AI only when there is new decision-relevant information, with better structured context.

### Phase 0: Keep Traders Paused Until Guards Exist

Status: already paused.

Do not resume trader cron until at least Phase 1 controls are implemented.

### Phase 1: Central AI Cost Guard

Add a central guard inside `gemini_cli_runner.py`.

Features:

- log every AI attempt to `trading.ai_call_log`;
- fields: script name, trader name, model, prompt chars, estimated tokens, response chars, duration, status, error class, job id;
- hard prompt budgets by category:
  - trader: 8K chars;
  - sentiment: 12K chars;
  - daily report: 30K chars;
  - evolution/incubator: 60K chars;
  - watchdog: 15K chars;
- per-hour request budgets by category;
- fail closed with `skipped_budget` instead of falling through to many models.

Quality impact:

- positive. It blocks waste and gives visibility without changing trading logic.

### Phase 2: Model Health Circuit Breaker

Add a model health cache.

Rules:

- if a model returns `exhausted`, timeout, or invalid/model-not-found more than N times in a rolling window, mark it unhealthy for 30-60 minutes;
- skip unhealthy models before making a CLI request;
- for trader calls, use at most one fallback after the primary model;
- route frequent trader calls to Flash-class models first;
- reserve Pro-class models for postmarket strategy/evolution/daily review.

Quality impact:

- neutral to positive. Frequent tactical decisions need low-latency reliable models; Pro is more useful for strategic synthesis.

### Phase 3: Fix MOEX Context Without Expanding Tokens

Fix `ai_paper_trader.py`/`market_research_context.py` mismatch:

- either include `engine` in MOEX context;
- or remove the `engine == stock` filter for MOEX;
- keep live trader market payload as compact price/change/top signals, not full windows.

Add assertions:

- if `snaps` is empty during MOEX session, skip AI and log `market_context_empty`;
- never call Gemini with `MARKET: {}`.

Quality impact:

- positive. Same or tiny token increase, much better decision context.

### Phase 4: Decision Delta Gating

Before calling Gemini for a trader, compute whether anything meaningful changed.

Inputs:

- latest prices/change;
- open positions;
- last trader decision;
- market regime;
- fresh KB strategic context timestamp.

Skip AI if:

- no position change;
- no new bar or no material price move;
- no new sentiment/news;
- last decision is still within TTL.

Suggested TTLs:

- scalper: 5 minutes only when volatility threshold is met;
- normal agents: 15-30 minutes;
- passive/value/index agents: 60 minutes or event-triggered.

Quality impact:

- positive if implemented as "no new information, no new decision". It preserves decisions when the state is unchanged.

### Phase 5: Batch Shared Context, Preserve Agent Independence

Split market analysis from agent decision.

Per market wave:

1. Build deterministic market snapshot.
2. Optionally call one "market summarizer" AI only if regime changed.
3. Feed the same short regime summary to agents.

For agents:

- keep individual agent prompts;
- but cache shared KB/market context;
- do not re-query KB per trader.

Quality impact:

- positive. Agents still make independent decisions, but they stop wasting tokens on repeated shared context.

### Phase 6: KB Query Cache

Create a `trading.ai_context_cache` table.

Cache:

- strategic alpha summary per market;
- risk level per market;
- per-trader lesson summary;
- TTL 30-60 minutes for intraday, 1 day for nightly lessons.

Rules:

- no per-trader LightRAG query inside every trader call;
- if KB answer is low-quality ("not enough information"), do not inject it into prompts;
- use last known good summary instead.

Quality impact:

- positive. The prompt gets a stable useful lesson instead of repeated "I do not have enough information".

### Phase 7: Reduce Trader Wave Frequency Intelligently

Replace fixed 5-minute full league waves with event-driven scheduling.

Recommended default:

- full league wave every 30 minutes;
- partial wave every 5 minutes only for agents whose strategy is relevant to the detected regime;
- immediate event wave only on large move/news/regime shift.

Examples:

- high volatility: scalper, price action, VSA, quant;
- range: contrarian, value, passive;
- trend breakout: Elliott, chaos, index, meta.

Quality impact:

- positive. The system calls the right agents more often instead of all agents always.

### Phase 8: Sentiment Oracle Redesign

Do not ask Gemini to "find news" without tools.

New flow:

1. Collect actual RSS/SearXNG/news texts deterministically.
2. Deduplicate by URL/title/content hash.
3. Score freshness and source reliability.
4. Batch all tickers into one Gemini call, or call only for tickers with fresh news.
5. Cache sentiment until new news arrives.

Quality impact:

- strong positive. Fewer calls and less hallucination.

### Phase 9: Daily Report Batching

Replace per-trader Gemini calls with one batched report prompt.

Prompt structure:

- table of all traders;
- positions/trades summary;
- ask for JSON map keyed by trader name.

Fallback:

- if batch fails, use deterministic report;
- optionally call AI only for top 3 winners, bottom 3 losers, and anomalies.

Quality impact:

- neutral to positive. The report sees league-wide context and reduces duplicate alpha context.

### Phase 10: Evolution/Incubator Compression

Do not send raw windows/indicators.

For evolution:

- summarize each trader over 7-14 days;
- include PnL, drawdown, trade count, win/loss, top mistakes, regime tags;
- send top examples only.

For incubator:

- aggregate per asset: trend regime, volatility, volume regime, support/resistance, selected indicators;
- include only statistically meaningful patterns;
- skip if data sufficiency is low.

Quality impact:

- positive. Less overfitting and less noise.

### Phase 11: Safe Resume Criteria

Resume traders only when:

- central `ai_call_log` exists;
- model circuit breaker exists;
- MOEX `MARKET: {}` bug is fixed;
- trader prompt budget is enforced;
- per-market request budget is enforced;
- dispatcher wave interval is increased or event-gated;
- KB context cache exists or per-trader KB query is disabled.

Initial safe resume settings:

- MOEX only;
- crypto remains paused;
- `AI_JOB_MAX_WORKERS=1` for first hour;
- full wave no more than every 30 minutes;
- trader primary model: Flash-class;
- max one fallback;
- alert if AI calls exceed 30/hour.

## Priority List

### Critical

1. Add `ai_call_log` and prompt/request budget enforcement in `gemini_cli_runner.py`.
2. Add model health circuit breaker and stop retrying exhausted Pro for every trader.
3. Fix MOEX `MARKET: {}` bug and skip AI when market context is empty.
4. Replace 5-minute full-league trader waves with TTL/event-gated scheduling.
5. Cache KB context and remove per-trader per-call LightRAG queries.

### Major

1. Batch daily report into one AI call.
2. Redesign sentiment oracle around real news input and batching.
3. Compress evolution/incubator datasets into statistical summaries.
4. Add data sufficiency gates before every strategic AI call.
5. Add dashboards/alerts for requests/hour, prompt chars/hour, failures/hour.

### Later

1. Build real AI backtester only with batch mode and strict budget caps.
2. Add per-agent strategy-specific feature selection.
3. Move Pro usage to strategic reviews only, not per-tick execution.
