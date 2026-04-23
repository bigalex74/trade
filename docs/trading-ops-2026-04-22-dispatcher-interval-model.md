# Trading Ops 2026-04-22: AI Dispatcher Interval Model

## Goal

Tune the MOEX AI trader launch model so the system stays responsive for intraday moves while avoiding runaway Gemini requests during degraded model/quota periods.

## Current Launch Model

The trader queue is still event/schedule driven through `/home/user/run_ai_job_dispatcher.sh` from cron once per minute. The wrapper runs dispatcher ticks every 25 seconds, up to 3 ticks per cron minute.

Intervals are calculated from local `Europe/Moscow` minutes since midnight, so values above 59 work correctly. For example, `90m` means 10:30, 12:00, 13:30, 15:00, and so on during the MOEX session.

Current safe-mode defaults:

- `AI_JOB_MAX_WORKERS=2`
- `AI_JOB_START_BATCH=1`
- `AI_JOB_DISPATCH_TICKS=3`
- `AI_JOB_DISPATCH_INTERVAL_SECONDS=25`
- `AI_JOB_FULL_WAVE_INTERVAL_MINUTES=90`
- `AI_JOB_FAST_WAVE_INTERVAL_MINUTES=10`
- `AI_JOB_EVENT_WAVE_INTERVAL_MINUTES=10`
- `AI_JOB_FULL_TRADER_TTL_MINUTES=20`
- `AI_JOB_FAST_TRADER_TTL_MINUTES=8`
- `AI_JOB_EVENT_TRADER_TTL_MINUTES=5`
- `AI_JOB_EVENT_FIVE_MIN_CHANGE_PCT=0.25`
- `AI_JOB_EVENT_HOUR_CHANGE_PCT=0.7`
- `AI_JOB_FAST_TRADERS=Scalper_Kesha,PriceAction_Nikita,VSA_Victor,Quant_Diana,Contrarian_Ricardo,Meta_Oracle`
- `AI_JOB_EVENT_TRADERS=Scalper_Kesha,PriceAction_Nikita,VSA_Victor,Quant_Diana,Contrarian_Ricardo,Meta_Oracle`

Reasoning:

- full wave is now a slower consensus refresh for all 11 traders;
- fast/event waves preserve the higher-value intraday set every 10 minutes when budget and queue allow;
- crypto AI remains disabled;
- short execution is still blocked by the risk engine until short/margin accounting is implemented.

## Budget Gate

`ai_job_dispatcher.py` now checks recent external trader AI requests before queueing a MOEX wave.

New tunables:

- `AI_JOB_BUDGET_AWARE=1`
- `AI_JOB_AI_REQUESTS_PER_TRADER_ESTIMATE=2.0`
- `AI_JOB_AI_CALL_RESERVE_TRADER=2`

The dispatcher queries `trading.ai_call_log` for the last-hour count where:

- `category='trader'`
- `request_allowed=TRUE`
- `status NOT IN ('model_skipped', 'budget_blocked')`

If remaining budget is below estimated wave demand, it writes `skipped_ai_budget` to `trading.ai_dispatcher_log` and does not enqueue the wave.

Trader request count is based on real external attempts, not prompt size:

- included: `trading.ai_call_log` rows where `request_allowed=TRUE`;
- excluded: `model_skipped` and `budget_blocked`;
- current analyzer ratio is `external_requests / started_trader_jobs`;
- prompt compaction changes cost and latency per request, but does not by itself reduce request count unless it reduces fallback failures or the number of AI calls per job.

## Model Cooldown

`ai_cost_guard.py` now creates and maintains:

- `trading.ai_model_cooldown`

The Gemini runner checks this table before trying each model. If a model receives `exhausted`, `quota`, or `capacity` degradation, it is put into cooldown immediately for subsequent trader jobs.

New tunables:

- `AI_MODEL_COOLDOWN_ENABLED=1`
- `AI_MODEL_COOLDOWN_EXHAUSTED_MINUTES_TRADER=60`
- `AI_MODEL_COOLDOWN_TIMEOUT_MINUTES_TRADER=15`
- `AI_MODEL_FAILURE_THRESHOLD=3`
- `AI_MODEL_HEALTH_WINDOW_MINUTES=30`

Behavior:

- quota/capacity/exhausted: immediate 60-minute trader cooldown by default;
- timeout: immediate 15-minute trader cooldown by default;
- parse/error failures still keep the older threshold guard to avoid blocking a model after one prompt-specific formatting issue;
- expired cooldown rows are automatically ignored and cleaned on health checks;
- `model_skipped` rows no longer store the full prompt, preventing debug-log bloat from skipped models.

## Structured Dispatcher Log

New table:

- `trading.ai_dispatcher_log`

It records:

- tick time and market;
- decision: `queued`, `skipped_pending`, `skipped_ai_budget`, `no_due_traders`, `no_wave_due`;
- wave reason: `full`, `fast`, `event`;
- inserted/due/candidate counts;
- queue/running/pending counts;
- event metrics;
- dispatcher config snapshot;
- details JSON, including AI budget details.

## Interval Analyzer

New script:

- `/home/user/ai_dispatcher_interval_analyzer.py`
- `/home/user/run_ai_dispatcher_interval_analyzer.sh`

Usage:

```bash
/home/user/run_ai_dispatcher_interval_analyzer.sh --hours 6 --limit 25
```

Healthy-model comparison:

```bash
/home/user/run_ai_dispatcher_interval_analyzer.sh --hours 6 --requests-per-job 1 --limit 15
```

The analyzer reads:

- `trading.ai_jobs`
- `trading.ai_call_log`
- `trading.ai_dispatcher_log`

It reports:

- job statuses and durations;
- queue delay;
- AI call statuses;
- active model cooldowns;
- external request count versus log rows;
- prompt size stats;
- dispatcher decisions;
- simulated jobs/hour, calls/hour, worker utilization, skipped waves/hour for alternate intervals.

## 2026-04-22 20:02 MSK Snapshot

Observed over 6 hours:

- MOEX trader jobs: 22 total, including queued/running jobs from the 20:00 full wave;
- external trader AI requests: 30;
- current last-hour AI budget: 29 used from limit 30, reserve 2, remaining 0;
- observed requests/job: about 2.0 because Gemini/model health is still degraded;
- analyzer safe candidate under current conditions: `full=90m`, `fast=10m`, `event=10m`.

When the model stabilizes near 1 external request per trader job, the analyzer shows faster schedules can be tested, including `full=30m`, `fast=10m`, `event=5-10m`, or tighter.

## Files Changed

- `/home/user/ai_job_dispatcher.py`
- `/home/user/run_ai_job_dispatcher.sh`
- `/home/user/ai_dispatcher_interval_analyzer.py`
- `/home/user/run_ai_dispatcher_interval_analyzer.sh`

## Verification

Passed:

```bash
/home/user/trading_venv/bin/python -m py_compile /home/user/ai_job_dispatcher.py /home/user/ai_dispatcher_interval_analyzer.py
bash -n /home/user/run_ai_job_dispatcher.sh /home/user/run_ai_dispatcher_interval_analyzer.sh
/home/user/run_ai_dispatcher_interval_analyzer.sh --hours 6 --limit 25
/home/user/run_ai_dispatcher_interval_analyzer.sh --hours 6 --requests-per-job 1 --limit 10
```
