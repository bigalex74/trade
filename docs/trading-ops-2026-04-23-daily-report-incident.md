# Trading Ops 2026-04-23: Daily Report Incident

## User Symptom

The user did not receive the expected daily MOEX report after the 2026-04-22 trading day.

Current check time:

- `2026-04-23 03:41-03:44 MSK`

## Root Cause

Cron did run the daily report at `2026-04-23 01:00 MSK`:

```text
[2026-04-23T01:00:01+03:00] ai_daily_report: start
...
[2026-04-23T01:04:03+03:00] ai_daily_report: success
```

But `ai_daily_report.py` internally skipped Telegram and ALGO KB upload because the quality gate failed:

```text
Daily report quality gate failed: failed_lessons=11, max_failed=2, traders=11.
Skipping Telegram and ALGO KB upload.
```

The quality gate failed because AI daily lessons degraded:

- `MoexDailyBatch`: `gemini-3-flash-preview` timeout;
- `MoexDailyStaff`: one model skipped by health guard, `gemini-2.5-flash` timeout;
- result: deterministic fallback lessons for all 11 traders.

The wrapper considered the script successful because the script returned normally after skipping output. This made cron look successful while the user received no report.

## Fix Applied

Updated `/home/user/ai_daily_report.py`:

- quality gate no longer blocks Telegram;
- if AI lessons are degraded, Telegram receives a deterministic fallback report with a warning;
- ALGO KB upload is still skipped when quality gate fails, so bad AI reports do not pollute KB;
- Telegram HTTP status is now printed for photo and chunks;
- added `AI_DAILY_REPORT_SKIP_AI=1` for manual deterministic report generation without Gemini calls.

Manual report was sent after the fix:

```text
[2026-04-23T03:44:07+03:00] ai_daily_report: start
Daily report quality gate failed: failed_lessons=11, max_failed=2, traders=11.
Sending Telegram fallback and skipping ALGO KB upload.
Telegram photo status=200
Telegram chunk status=200 chars=1301
Telegram chunk status=200 chars=1435
Telegram chunk status=200 chars=751
[2026-04-23T03:44:15+03:00] ai_daily_report: success
```

## Current Scheduling Status

Active cron lines:

- stock AI dispatcher: every minute through `/home/user/run_ai_job_dispatcher.sh`;
- matching engine: every minute during MOEX hours through `/home/user/run_matching_engine_once.sh`;
- hourly MOEX report: queued by dispatcher during MOEX session, last observed reports sent successfully;
- daily MOEX report: `0 1 * * * /home/user/run_ai_daily_report.sh`;
- postmarket jobs:
  - `00:05` `/home/user/run_ai_evolution.sh`;
  - `00:30` `/home/user/run_ai_genetic_incubator.sh`;
  - `00:45` `/home/user/run_ai_watchdog_analyzer.sh`;
  - `01:00` `/home/user/run_ai_daily_report.sh`.

Crypto remains disabled by cron comments.

## Other Nightly Findings

Postmarket status after the 2026-04-22 session:

- `ai_genetic_incubator`: succeeded and uploaded `strategy_alpha_2026-04-23.md`;
- `ai_evolution`: ran, but AI was blocked by prompt size `62764 > 60000`; no ALGO KB upload;
- `ai_watchdog_analyzer`: ran, but Gemini timed out; no KB upload;
- `ai_daily_report`: ran, originally skipped Telegram due quality gate; fixed and manually resent.

## Trading System Status

At `03:44 MSK`, the MOEX market is closed, so no trader jobs should be actively running.

Last 24h MOEX status:

- trader jobs: many succeeded, many failed due Gemini degradation/capacity;
- orders: 59 filled in the last 24h;
- hourly reports: succeeded and sent to Telegram;
- dispatcher budget gate skipped several waves when AI call budget was insufficient.

## Verification

Passed:

```bash
/home/user/trading_venv/bin/python -m py_compile /home/user/ai_daily_report.py
AI_TEST_MODE=1 AI_DAILY_REPORT_SKIP_AI=1 /home/user/trading_venv/bin/python /home/user/ai_daily_report.py
AI_DAILY_REPORT_SKIP_AI=1 /home/user/run_ai_daily_report.sh
```

Manual real Telegram send returned HTTP 200 for the chart and all message chunks.
