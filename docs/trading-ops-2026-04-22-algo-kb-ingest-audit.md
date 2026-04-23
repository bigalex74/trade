# ALGO KB ingest audit - 2026-04-22

## Context

User reported that `algo.bigalexn8n.ru` did not show normal knowledge-base records from trading scripts.

Local LightRAG ALGO instance:

- URL: `http://127.0.0.1:9624`
- Container: `lightrag-algo`
- Status at audit time: healthy
- Documents before live repair tests: 33 processed, 0 failed

## Findings

1. `/documents/upload` accepts only `multipart/form-data` with a file field.
2. Some scripts posted JSON to `/documents/upload`; LightRAG returns HTTP 422 for that shape.
3. Several scripts wrote text files into `/home/user/lightrag-algo/inputs`, but the previous periodic `/documents/scan` cron was removed, so file-only writes no longer reached the index.
4. Upload callers did not check response status or print `track_id`, so failed writes were invisible in cron logs.
5. Nightly ALGO KB records for 2026-04-22 contained bad placeholder content:
   - `deep_dive_2026-04-22.md`: `Analysis failed.`
   - `strategy_alpha_2026-04-22.md`: `Incubation failed.`
   These were caused by the older Gemini CLI `--output-format markdown` issue fixed earlier.

## Changes

Added `/home/user/algo_kb_client.py`:

- `upload_file_to_algo_kb()` uses `/documents/upload` for real files.
- `insert_text_to_algo_kb()` uses `/documents/text` for generated text.
- Both functions validate HTTP status and LightRAG insert status.
- Both functions log `status` and `track_id`.
- `wait_for_algo_kb_track()` polls `/documents/track_status/{track_id}` for diagnostics.

Updated scripts:

- `/home/user/ai_evolution.py`
  - Uses shared file upload helper.
  - Skips ALGO KB upload when the report is only `Analysis failed.`.
- `/home/user/ai_genetic_incubator.py`
  - Uses shared file upload helper.
  - Skips ALGO KB upload when the report is only `Incubation failed.`.
- `/home/user/ai_macro_sensei.py`
  - Uses shared file upload helper and logs `track_id`.
- `/home/user/ai_daily_report.py`
  - Now writes the final MOEX daily report into ALGO KB via `/documents/text`.
- `/home/user/ai_crypto_daily_report.py`
  - Fixed `save_to_knowledge_base()` to use `/documents/text`.
  - Now calls the save function for each crypto trader lesson when crypto reports are re-enabled.
- `/home/user/trading_core_market_pipeline.py`
  - Fixed macro update writes to use `/documents/text`.
  - Logs failures instead of silently swallowing them.
- `/home/user/news_collector.py`
  - Keeps local file write, and also inserts the report directly into ALGO KB.
- `/home/user/algo_analyzer.py`
  - Keeps local file write, and also inserts the report directly into ALGO KB.
- `/home/user/run_moex_collector.sh`
  - Replaced `/documents/scan` dependency with direct `/documents/text` insert for portfolio status.

## Live Verification

Ran:

- `/home/user/trading_venv/bin/python3 /home/user/news_collector.py`
- `/home/user/trading_venv/bin/python3 /home/user/algo_analyzer.py`

LightRAG accepted and processed:

- `market_news_2026-04-22_0646.txt`
  - `track_id=insert_20260422_034624_c179071c`
  - status: `processed`
  - chunks: 1
- `algo_signals_2026-04-22_0646.txt`
  - `track_id=insert_20260422_034636_35b5853d`
  - status: `processed`
  - chunks: 1

Document counts after verification:

- processed: 35
- failed: 0
- pending: 0
- processing: 0

Query verification:

- Query by file names was weak because LightRAG indexes content, not file-source metadata as a reliable semantic target.
- Query by content retrieved the new market/analytics facts, including USD/RUB 75.6525 and the fresh Smart Analytics report.

## Remaining Notes

- `news_collector.py` and `algo_analyzer.py` are not active in the current crontab because the legacy `run_moex_collector.sh` line is disabled.
- Active daily ALGO KB writers after this change are the nightly AI scripts and `ai_daily_report.py`.
- If frequent intraday ALGO KB context is desired, add a small dedicated cron for a concise market summary rather than indexing every candle.

## Follow-up - 2026-04-22 07:00 MSK

Deleted bad placeholder ALGO KB documents:

- `deep_dive_2026-04-22.md`
  - old id: `doc-0b438492a90b1cb5a81dcce34df1799c`
  - content: `Analysis failed.`
- `strategy_alpha_2026-04-22.md`
  - old id: `doc-78f4fe29c66a52cb98cbe7cebb25c3be`
  - content: `Incubation failed.`

Deletion was run through `/documents/delete_document` with `delete_file=true` and `delete_llm_cache=true`.
Container logs confirmed both enqueued files were removed.

Added guardrails:

- `/home/user/algo_kb_client.py` now rejects empty text, too-short text, and exact placeholders:
  - `Analysis failed.`
  - `Incubation failed.`
  - `Audit failed.`
  - `Error`
  - `No data.`
  - `KB Unavailable.`
- File upload helper validates text before upload.
- Text insert helper validates text before insert.
- `ai_evolution.py` and `ai_genetic_incubator.py` now skip failed reports before local file creation and before KB upload.
- `ai_watchdog_analyzer.py` now skips `Audit failed.` before writing/uploading to the general KB.

Added compact scheduled ALGO KB summary:

- New script: `/home/user/algo_kb_market_summary.py`
- New wrapper: `/home/user/run_algo_kb_market_summary.sh`
- Cron:
  - `40 8 * * 1-5 /home/user/run_algo_kb_market_summary.sh >> /home/user/logs/algo_kb_market_summary.log 2>&1`
- It reads current `market_research` context and writes one concise daily MOEX market snapshot to ALGO KB.
- It does not use Gemini, old static news, or `/documents/scan`.

Live verification:

- Guard smoke test blocked `Analysis failed.`, `Incubation failed.`, `Audit failed.`, and empty text.
- Live wrapper run inserted:
  - `moex_market_summary_2026-04-22_0700.txt`
  - `track_id=insert_20260422_040029_d05f0886`
  - status: `processed`
  - chunks: 4
- ALGO KB after deletion and summary insert:
  - processed: 34
  - failed: 0
  - bad placeholder docs: 0
