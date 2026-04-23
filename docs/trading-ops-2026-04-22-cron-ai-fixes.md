# Trading Ops: Cron And AI Script Fixes 2026-04-22

## Context

The system was reviewed after crypto AI traders were paused so the next work window can focus on MOEX exchange trading. The audit found two scheduled jobs to disable and several AI scripts failing because their Gemini CLI invocation no longer matched the installed CLI.

## Cron Changes

- Disabled `/home/user/n8n-backups/sync_n8n.sh` in crontab.
- Removed the daily `curl -X POST http://localhost:9624/documents/scan` LightRAG scan entry.
- Left MOEX market research, AI job queue, matching engine, watchdogs, and nightly MOEX analytics enabled.
- Crypto jobs remain paused:
  - `crypto_pipeline.py` is commented out.
  - `ai_crypto_daily_report.py` is commented out.
  - `AI_ENABLE_CRYPTO_AI` defaults to `0`.

## Code Changes

- `/home/user/gemini_cli_runner.py`
  - `call_ai_markdown_with_fallback()` now uses Gemini CLI `--output-format text`.
  - This fixes the installed CLI error where `markdown` is not an accepted output format.

- `/home/user/ai_sentiment_oracle.py`
  - Replaced the single `gemini-3.1-flash-lite-preview` model with fallback models:
    `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-3.1-flash-lite-preview`.
  - Added test controls:
    - `AI_SENTIMENT_MAX_TICKERS`
    - `AI_SENTIMENT_SLEEP_SECONDS`

- `/home/user/ai_evolution.py`
  - Removed obsolete `gemini-1.5-pro-preview`.
  - Added faster fallback models including `gemini-2.5-flash-lite`.
  - Added `AI_TEST_MODE=1` to use small synthetic data and skip KB upload/Telegram.

- `/home/user/ai_genetic_incubator.py`
  - Added faster fallback models including `gemini-2.5-flash-lite`.
  - Added `AI_TEST_MODE=1` to use small synthetic data and skip KB upload/Telegram.

- `/home/user/ai_watchdog_analyzer.py`
  - Added faster fallback models including `gemini-2.5-flash-lite`.
  - Added `AI_TEST_MODE=1` to use a synthetic log summary and skip KB upload/Telegram.

- `/home/user/ai_daily_report.py`
  - Removed obsolete `gemini-1.5-pro-preview`.
  - Added faster fallback models including `gemini-2.5-flash-lite`.
  - Added `AI_TEST_MODE=1` and `AI_DAILY_REPORT_MAX_TRADERS`.
  - Telegram sending is skipped when token is absent or test mode is enabled.

- `/home/user/ai_crypto_daily_report.py`
  - Removed obsolete `gemini-1.5-pro-preview`.
  - Added faster fallback models including `gemini-2.5-flash-lite`.
  - Script remains disabled in cron while crypto is paused.

## Tests

- Python compilation passed for:
  - `gemini_cli_runner.py`
  - `ai_sentiment_oracle.py`
  - `ai_evolution.py`
  - `ai_genetic_incubator.py`
  - `ai_watchdog_analyzer.py`
  - `ai_daily_report.py`
  - `ai_crypto_daily_report.py`
  - `ai_macro_sensei.py`

- Shell syntax passed for:
  - `run_ai_job_dispatcher.sh`
  - `run_logrotate_trading.sh`
  - `system_watchdog.sh`
  - `backup_project.sh`

- Runtime smoke tests passed:
  - `ai_sentiment_oracle.py` with one ticker and no sleep updated SBER sentiment successfully.
  - `ai_evolution.py` in `AI_TEST_MODE=1` completed and skipped external upload/Telegram.
  - `ai_genetic_incubator.py` in `AI_TEST_MODE=1` completed and skipped external upload/Telegram.
  - `ai_watchdog_analyzer.py` in `AI_TEST_MODE=1` completed and skipped external upload/Telegram.
  - `ai_daily_report.py` in `AI_TEST_MODE=1` with one trader completed and skipped Telegram.

## Observations

- Current Gemini Pro models often return `exhausted`, so scripts now prefer practical flash fallbacks after trying Pro.
- Old log files still contain earlier errors (`output-format markdown`, missing `gemini`, `gemini-1.5-pro-preview` not found). Those entries predate this fix.
- After tests, no `gemini`, `ai_job_worker`, `ai_crypto_trader`, or `ai_paper_trader` processes were left running.

## Re-enable Notes

- To re-enable `sync_n8n.sh`, uncomment its `DISABLED 2026-04-22 user requested` crontab line.
- To restore LightRAG scan, add back:
  `0 1 * * * curl -X POST http://localhost:9624/documents/scan`
- To re-enable crypto next week:
  - set `AI_ENABLE_CRYPTO_AI=1`;
  - uncomment `crypto_pipeline.py`;
  - uncomment `ai_crypto_daily_report.py`.
