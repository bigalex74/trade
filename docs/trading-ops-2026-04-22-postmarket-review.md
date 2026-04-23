# Post-market scripts review - 2026-04-22

Scope: active cron jobs that run after 00:00 MSK and are related to the trading/post-market pipeline or its supporting infrastructure.

## Active jobs after 00:00

- `00:00` `/home/user/market_research_maintenance.py cleanup-intraday-history`
  - Deletes previous-day `1m` and `1h` rows from `market_research.raw.candle`.
- `00:05` `/home/user/ai_evolution.py`
  - Builds a retrospective daily trading audit and uploads `deep_dive_YYYY-MM-DD.md` to ALGO KB.
- `00:30` `/home/user/ai_genetic_incubator.py`
  - Looks for weekly asset patterns and uploads `strategy_alpha_YYYY-MM-DD.md` to ALGO KB.
- `00:45` `/home/user/ai_watchdog_analyzer.py`
  - Scans logs, asks Gemini for SRE recommendations, uploads `tech_audit_YYYY-MM-DD.md` to the general KB.
- `01:00` `/home/user/ai_daily_report.py`
  - Queries ALGO/general KB, audits each trader, sends Telegram, writes final MOEX daily report to ALGO KB.
- `03:00` `/home/user/n8n-backups/backup_to_yandex.sh`
  - Creates and uploads n8n backup archive to Yandex Disk.
- `03:17` `/home/user/run_logrotate_trading.sh`
  - Rotates trading/n8n logs.
- `04:00` `/home/user/backup_project.sh`
  - Runs `git add .`, commits, and pushes the full `/home/user` worktree.

## Current evidence

- Last post-market AI cron logs from 2026-04-22 were generated before the Gemini `--output-format text` fix and show failures from old `--output-format markdown`.
- Current `gemini_cli_runner.py` now uses `text` for markdown responses and has a 120 second per-call budget.
- Current ALGO KB guard blocks exact placeholders such as `Analysis failed.` and `Incubation failed.`.
- ALGO KB currently has 34 processed docs, 0 failed docs, and no `Analysis failed.` / `Incubation failed.` placeholders.
- General KB still contains one bad processed document:
  - `tech_audit_2026-04-22.md`
  - content summary: `Audit failed.`
  - id: `doc-dc7074b939daa7bf24be6598fdfbd513`

## Pluses

- The post-market sequence is easy to understand: cleanup, strategy/evolution, tech audit, consolidated daily report.
- Market data cleanup logs exact deleted row counts as JSON.
- Gemini calls now run in a clean Gemini home/workdir and disable MCP servers.
- Gemini calls use a shared slot pool and per-call timeout in `gemini_cli_runner.py`.
- ALGO KB writes now have a shared client and placeholder guard for the scripts already migrated.
- Crypto cron remains disabled, so the night cycle is focused on MOEX.
- The new 08:40 ALGO summary is compact, deterministic, and does not depend on Gemini.

## Minuses

- Nightly AI jobs are still launched directly from cron rather than through per-script wrappers with whole-process `flock` and `timeout`.
- The daily report can still call Gemini many times in one process because it loops over all traders.
- The nightly reports do not have a single run table/status table, so success/failure is spread across plain logs and KB side effects.
- The SRE audit still uses a custom upload path to the general KB, not the guarded shared ALGO KB client pattern.
- Some prompts send large raw payloads to Gemini rather than compact pre-aggregated summaries.
- Backup scripts are mixed into the same post-midnight window and have reliability/security problems.

## Critical fixes

1. Add whole-process wrappers for nightly AI scripts.
   - Current cron runs `ai_evolution.py`, `ai_genetic_incubator.py`, `ai_watchdog_analyzer.py`, and `ai_daily_report.py` directly through Infisical.
   - `gemini_cli_runner.py` protects individual calls, but not the full script.
   - `ai_daily_report.py` can make one AI call per trader plus staff suggestions.
   - Fix: create `run_ai_evolution.sh`, `run_ai_genetic_incubator.sh`, `run_ai_watchdog_analyzer.sh`, `run_ai_daily_report.sh` with `flock`, `timeout`, timestamps, and explicit exit status.

2. Prevent `ai_daily_report.py` from writing low-quality AI failure reports to ALGO KB.
   - Fallback at `/home/user/ai_daily_report.py:36` returns `{"work":"Error","resume":"Error","tuning":"Error"}`.
   - Upload at `/home/user/ai_daily_report.py:113-119` writes the full report if the process reaches that point.
   - Current placeholder guard does not block a long report containing many `Error` sections.
   - Fix: count failed trader analyses; skip KB/Telegram if failures exceed threshold; write an ops failure status instead.

3. Clean the bad general KB document and migrate SRE audit upload to a guarded client.
   - `/home/user/ai_watchdog_analyzer.py:77-78` posts a file directly and does not check response status.
   - General KB has `tech_audit_2026-04-22.md` with `Audit failed.`.
   - Fix: delete that document, add a general-KB equivalent of the guarded client, and block placeholder uploads there too.

4. Fix Yandex backup false-success handling.
   - `/home/user/n8n-backups/backup_to_yandex.sh:78-81` uses `UPLOAD_STATUS=$(curl ...) || true`, then checks `$?`; this makes failed uploads look successful.
   - Fix: capture curl status before `|| true`, or remove `|| true` and handle failure explicitly.

5. Replace `/home/user/backup_project.sh`.
   - `/home/user/backup_project.sh:4-11` runs `git add .`, commits everything in `/home/user`, and pushes `master`.
   - This can include generated files, large artifacts, local configs, secrets, temporary data, and unrelated work.
   - Fix: replace with a scoped backup script using explicit include paths, `.gitignore`, no blind `git add .`, and a separate private backup remote if needed.

## Major fixes

1. Move intraday cleanup after post-market analysis or keep a compressed raw archive.
   - `/home/user/market_research_maintenance.py:40-81` deletes previous-day raw `1m` and `1h` candles at `00:00`.
   - Current AI scripts mostly use derived windows, but this removes raw data before deeper post-day diagnostics can use it.
   - Fix: run cleanup after 01:00, or archive raw intraday rows before deletion.

2. Add data sufficiency gates before Gemini calls.
   - `ai_evolution.py` and `ai_genetic_incubator.py` call Gemini even when data can be too thin or test-like.
   - Current local `strategy_alpha_2026-04-22.md` says it cannot analyze because the dataset is too small.
   - Fix: require minimum ticker count/window count/trade count; otherwise emit a structured skip status and do not call AI.

3. Reduce prompt size and sanitize payloads.
   - `/home/user/ai_evolution.py:84-91` dumps daily market/trade data directly into the prompt.
   - `/home/user/ai_genetic_incubator.py:52-57` dumps weekly history directly.
   - `/home/user/ai_watchdog_analyzer.py:46-62` summarizes all logs by scanning the last 1000 lines per file.
   - Fix: pre-aggregate compact metrics, cap tickers/rows, redact secrets/tokens/URLs before sending to Gemini.

4. Add a nightly run status table.
   - Current system relies on logs and KB artifacts.
   - Fix: table like `ops.nightly_job_run(job_name, started_at, finished_at, status, model_id, track_id, error_summary)`.

5. Persist useful daily report outcomes back into trader state.
   - `ai_daily_report.py` generates tuning text but does not update `trading.trader_config`.
   - Fix: either update learned traits with a guarded strategy, or explicitly make daily report read-only and document that evolution owns learning.

6. Escape Telegram HTML in `ai_daily_report.py`.
   - `/home/user/ai_daily_report.py:96-97` inserts model output directly into HTML message fields.
   - Fix: `html.escape()` all AI-provided text before Telegram send.

7. Add post-run KB verification for every KB upload.
   - ALGO client has `wait_for_algo_kb_track()`, but nightly scripts do not use it.
   - Fix: wait for processed/failed status or record `track_id` into the run status table.

8. Remove stale generated local files.
   - Local files such as `deep_dive_2026-04-22.md`, `strategy_alpha_2026-04-22.md`, and `tech_audit_2026-04-22.md` remain in `/home/user`.
   - Fix: write generated reports to `/home/user/reports/YYYY-MM-DD/` and clean/rotate them.

## Suggested priority

1. Critical 1, 2, 3: wrappers/status/KB quality gate.
2. Critical 4, 5: backup correctness and backup scope.
3. Major 1, 2, 3: raw data timing, data gates, prompt compaction.
4. Major 4, 5, 6, 7, 8: observability and cleanup polish.
