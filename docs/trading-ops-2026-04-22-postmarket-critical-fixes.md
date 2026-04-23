# Trading Ops: Postmarket Critical Fixes 2026-04-22

## Context

The postmarket jobs after midnight were reviewed after crypto traders were paused. The goal was to make the nightly AI/report/backup contour bounded, non-overlapping, and resistant to bad knowledge-base writes.

## Implemented Critical Fixes

1. Added whole-process wrappers for postmarket AI jobs:
   - `/home/user/run_postmarket_ai_job.sh`
   - `/home/user/run_ai_evolution.sh`
   - `/home/user/run_ai_genetic_incubator.sh`
   - `/home/user/run_ai_watchdog_analyzer.sh`
   - `/home/user/run_ai_daily_report.sh`

   The shared wrapper uses `flock`, `/usr/bin/timeout`, Infisical, and the trading venv. Default timeout is 30 minutes, with shorter per-job timeouts for evolution/incubator/watchdog and 40 minutes for the final daily report.

2. Updated cron so postmarket AI scripts run only through the wrappers:
   - `00:05` evolution
   - `00:30` strategy incubator
   - `00:45` technical watchdog analyzer
   - `01:00` final daily report

3. Hardened `ai_daily_report.py`:
   - rejects trader lesson placeholders like `AI analysis failed`;
   - escapes AI-generated text before Telegram HTML rendering;
   - skips Telegram and ALGO KB upload if too many trader analyses fail.

4. Hardened KB writes:
   - `algo_kb_client.py` now supports ALGO KB and general KB uploads through one guarded client;
   - rejects empty, too-short, placeholder, and low-quality refusal texts before LightRAG upload;
   - new blocked patterns include `analysis failed`, `incubation failed`, `audit failed`, insufficient-dataset refusals, and similar useless reports.

5. Migrated `ai_watchdog_analyzer.py` to guarded general KB upload.

6. Removed bad KB entries:
   - ALGO KB: no remaining `Analysis failed` or `Incubation failed` documents found.
   - General KB: deleted stale `Audit failed` / empty failed tech audit records; no remaining failed records found.

7. Fixed Yandex backup false-success handling:
   - `/home/user/n8n-backups/backup_to_yandex.sh` now uses `set -euo pipefail`;
   - upload uses `curl --fail`;
   - upload failure logs the real curl exit/response, sends notification, removes the archive, and exits nonzero;
   - missing `YANDEX_OAUTH_TOKEN` is now an explicit failure.

8. Replaced blind project backup:
   - `/home/user/backup_project.sh` no longer runs `git add .`, commit, or push;
   - it creates a scoped `tar.gz` archive with the trading ops scripts/docs only;
   - local retention is 14 days.

## Verification

Completed checks:

- `bash -n` passed for all new wrappers, `backup_project.sh`, and `backup_to_yandex.sh`.
- `py_compile` passed for `algo_kb_client.py`, `ai_daily_report.py`, `ai_watchdog_analyzer.py`, `ai_evolution.py`, and `ai_genetic_incubator.py`.
- `run_postmarket_ai_job.sh` smoke-tested with `/bin/echo` and confirmed it passes `--allowed-mcp-server-names __none__`.
- `run_postmarket_ai_job.sh` lock skip path smoke-tested: second run exits cleanly when the lock is held.
- KB validator smoke-tested against exact placeholders and a real low-quality `strategy_alpha_2026-04-22.md` refusal.
- `backup_project.sh` executed successfully and created `/home/user/project_backup/scoped_archives/trading_ops_2026-04-22_13-28-38.tar.gz`.
- Archive content was inspected and contains the intended scoped trading ops files.
- ALGO KB and general KB were checked for failed/bad records after cleanup.

Not live-tested:

- Yandex upload was not forced manually, to avoid an extra external backup upload. It was syntax-checked and reviewed statically.
- Full postmarket AI generation was not forced manually during the trading session, to avoid consuming Gemini slots and creating duplicate reports.

## Repeat Review Findings

Resolved:

- Postmarket scripts are now bounded by timeout and lock.
- Bad placeholder KB writes are blocked before upload.
- General KB tech audit upload uses the same guarded path as ALGO KB.
- Blind full-home git backup has been replaced by scoped archive backup.
- `sync_n8n.sh` remains disabled in cron.
- Crypto cron jobs remain disabled until next week.

Remaining risks:

- During MOEX hours, live trader Gemini jobs still occupy the shared Gemini slots. Any manual AI smoke test without a separate test lock prefix may wait for a slot.
- Current active trader prompts still show weak context in places: `MARKET: {}` and KB responses like "I don't have enough information". This is not a postmarket runner failure, but it reduces trader decision quality.
- Old cron logs still contain Infisical noise and pre-fix `--output-format markdown` errors. The current `gemini_cli_runner.py` uses supported `--output-format text` for markdown-style reports.
- `ai_daily_report.py` can still spend a long time because it calls Gemini per trader. The process is now bounded, but the design is still expensive.
- Evolution/incubator still need explicit data sufficiency gates before calling Gemini, so they do not generate "insufficient dataset" reports.

## Next Work Plan

Critical if the next nightly run fails:

1. Add a `trading.nightly_job_run` table and record start/end/status/track_id for each postmarket job.
2. Add `wait_for_*_track` support for both ALGO and general KB after uploads, so cron can detect failed LightRAG background processing.

Major planned improvements:

1. Add data sufficiency gates to evolution/incubator/watchdog before Gemini calls.
2. Compact large prompts and remove noisy/error-only context before sending to Gemini.
3. Move final raw-data cleanup after the whole postmarket chain, or archive raw context before cleanup.
4. Reduce `ai_daily_report.py` from per-trader Gemini calls to batched or top-N analysis.
5. Add structured postmarket status report to Telegram with green/yellow/red job statuses.
6. Rotate local generated report files like `deep_dive_*.md`, `strategy_alpha_*.md`, and `tech_audit_*.md`.
