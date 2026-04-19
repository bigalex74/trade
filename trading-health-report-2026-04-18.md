# Trading Health Report

Generated: 2026-04-18 15:02 MSK

## Summary

Trading workflows are operational.

- Host `cron` is installed and actively triggering `news` and `candle` internal webhooks on schedule.
- `digest` and `candle backfill` were manually triggered at `2026-04-18 14:58:06 MSK` and confirmed via `market_research` DB changes.
- `n8n` execution history is misleading for these workflows because workflow settings use `saveDataSuccessExecution = "none"`.

## Workflow Status

- `MOEX | News Research Feed` (`v77tZsa4wOtbPqwN`) — `active=true`
- `MOEX | Candle Research Feed` (`BQM9Qy3rgMDURm1f`) — `active=true`
- `MOEX | Daily Research Digest` (`Cefl1Xb6o3ceFoO0`) — `active=true`
- `MOEX | Candle Backfill` (`eGLrEdlnVD6ZbHUj`) — `active=true`
- `MOEX | News Backfill` (`kYbCBufdz0XGWpiF`) — `active=false`

## Cron Evidence

Recent `news` host log:

- `2026-04-18 14:33:01 MSK` — trigger accepted
- `2026-04-18 14:48:01 MSK` — trigger accepted

Recent `candle` host log:

- `2026-04-18 14:35:01 MSK` — trigger accepted
- `2026-04-18 14:50:01 MSK` — trigger accepted

## Market Research DB

State at verification time:

- `raw.candle = 22864`, last `collected_at = 2026-04-18 14:58:08 MSK`
- `analytics.instrument_snapshot = 1130`, last `snapshot_at = 2026-04-18 14:50:07 MSK`
- `analytics.research_digest = 3`, last `generated_at = 2026-04-18 14:58:07 MSK`
- `ingest.lightrag_document_log` for `analytics.instrument_snapshot = 114`, last `published_at = 2026-04-18 14:50:09 MSK`
- `ingest.lightrag_document_log` for `raw.news_item = 65`, last `published_at = 2026-04-17 21:22:09 MSK`
- `meta.workflow_cursor = 100`, last `updated_at = 2026-04-18 14:58:08 MSK`

## Manual Verification

### Daily Research Digest

Manual internal webhook trigger time:

- `2026-04-18 14:58:06 MSK`

Confirmed result:

- `analytics.research_digest` increased from `2` to `3`
- latest digest timestamp became `2026-04-18 14:58:07 MSK`

### Candle Backfill

Manual internal webhook trigger time:

- `2026-04-18 14:58:06 MSK`

Confirmed result:

- `raw.candle` increased from `19204` to `22864`
- `meta.workflow_cursor` advanced to `2026-04-18 14:58:08 MSK`
- fresh backfill cursor keys appeared for:
  - `AFLT`
  - `ALRS`
  - `CHMF`

## Execution History Caveat

The reason fresh successful cron/webhook runs do not show up in normal `n8n` execution history is workflow configuration:

- `saveDataSuccessExecution = "none"`
- `saveDataErrorExecution = "all"`
- `saveManualExecutions = true`

Practical implication:

- successful trigger/webhook executions are not reliable as the primary health signal in the `n8n` UI/API
- DB timestamps and host cron logs are the authoritative runtime signal for these workflows

## Residual Notes

- Old error executions still exist for:
  - legacy `MOEX RSS Trigger`
  - earlier candle timeout runs from `2026-04-17`
- These do not match the current live state of the production feed.

