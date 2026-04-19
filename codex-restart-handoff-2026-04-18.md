# Codex Restart Handoff

Generated: 2026-04-18 14:24 Europe/Moscow

## 1. Why this file exists

This file is the authoritative handoff for the next Codex session after restart.
The immediate reason for restart is to relaunch Codex without the current sandbox restrictions so the next session can work directly with host-side operations, Infisical, sudo, docker, and restart paths.

The previous session completed the MOEX trade-research infrastructure setup far enough to prove that:

- host cron orchestration works;
- the market research database really receives data;
- the separate trade LightRAG knowledge base (`tradekb`) really receives published documents;
- the remaining blocking step is the host-side Infisical cutover and final cleanup.

## 2. Codex local config change already applied

File changed:
- `/home/user/.codex/config.toml`

Added:
```toml
sandbox_mode = "danger-full-access"
approval_policy = "on-request"
```

Implication:
- after restart, Codex should run without the current read-only/workspace sandbox constraints;
- approval remains interactive and sane (`on-request`) rather than fully disabled;
- if the restarted session still shows errors like `sudo: no new privileges`, then the user is still launching inside some outer sandbox/wrapper and the problem is no longer Codex config.

Recommended launch after restart:
```bash
codex
```

Optional explicit launch if needed:
```bash
codex -s danger-full-access -a on-request
```

## 3. User goal and project context

Longer-term user goal:
- build a MOEX-focused research and trading-assistant stack;
- collect market information, candles, and news;
- enrich a dedicated trade knowledge base;
- eventually use that infrastructure for research-assisted trading workflows.

Immediate infrastructure goal in this session:
- separate the trade knowledge base from unrelated LightRAG data;
- route MOEX workflows to the dedicated trade KB and dedicated market research database;
- make scheduling reliable;
- prepare secret migration into Infisical.

## 4. Core architecture as of end of session

### 4.1 Main components

1. `n8n`
- domain: `https://bigalexn8n.ru`
- compose dir: `/home/user/n8n-docker`

2. Dedicated trade LightRAG / KB
- domain: `https://tradekb.bigalexn8n.ru`
- purpose: only trade/MOEX-related knowledge, separate from the old mixed KB

3. Market research Postgres
- dedicated DB/roles/credentials were already prepared before the final handoff stage
- n8n credentials created and wired into workflows:
  - `Market Research Postgres RO`
  - `Market Research Postgres RW`

4. Infisical
- domain: `https://secrets.bigalexn8n.ru`
- local workspace file exists:
  - `/home/user/n8n-docker/.infisical.json`
- current contents:
  - `workspaceId = 1d44cf0c-94b5-4e64-bccd-9c4da8843fec`
  - `defaultEnvironment = dev`

### 4.2 Important current limitation discovered in the old session

The old session was sandboxed and could not reliably do:
- `sudo`
- host docker control
- dbus/system keyring access used by Infisical CLI

This is why the session stopped at a staged Infisical cutover rather than a fully executed one.

## 5. n8n workflows currently relevant

### 5.1 Production MOEX workflows

1. `MOEX | News Research Feed`
- workflow id: `v77tZsa4wOtbPqwN`

2. `MOEX | Candle Research Feed`
- workflow id: `BQM9Qy3rgMDURm1f`

3. `MOEX | Daily Research Digest`
- workflow id: `Cefl1Xb6o3ceFoO0`

4. `MOEX | Candle Backfill`
- workflow id: `eGLrEdlnVD6ZbHUj`

5. `MOEX | News Backfill`
- workflow id: `kYbCBufdz0XGWpiF`
- not central to the very next step, but it exists

### 5.2 What changed in `MOEX | News Research Feed`

This workflow was materially refactored.

Key changes:
- removed unstable `RSS Feed Trigger` as the production entrypoint;
- added `Read MOEX RSS` node;
- added `Internal Cron Webhook` node;
- feed now inserts/updates raw RSS items into `raw.news_item`;
- downstream publish path only continues for rows returned as truly new via `RETURNING (xmax = 0) AS inserted`;
- separate upsert maintained in `raw.news_instrument_match`.

Important current nodes in that workflow:
- `Internal Cron Webhook`
- `Schedule Trigger`
- `Read MOEX RSS`
- `Prepare Incoming News`
- `Upsert Raw News Items`
- `Keep Fresh News`
- `Get Watchlist`
- `Append News And Watchlist`
- `Match News To Watchlist`
- `Upsert News Match`
- `Push News To LightRAG`
- `Log News Publish`

Webhook path:
- `moex-news-feed-int-b0e19a6a`

Important SQL targets:
- `raw.news_item`
- `raw.news_instrument_match`
- `ingest.lightrag_document_log`

### 5.3 What changed in `MOEX | Candle Research Feed`

This workflow also has an internal cron webhook fallback.

Webhook path:
- `moex-candle-feed-int-7c1a55d9`

Important SQL targets:
- `raw.candle`
- `analytics.instrument_snapshot`
- `meta.workflow_cursor`
- `ingest.lightrag_document_log`

LightRAG publish node:
- posts to `http://127.0.0.1:9623/documents/text`

### 5.4 Internal cron webhooks added to 4 workflows

Webhook paths:
- News: `moex-news-feed-int-b0e19a6a`
- Candle: `moex-candle-feed-int-7c1a55d9`
- Backfill: `moex-backfill-int-e95bf233`
- Digest: `moex-digest-int-6fa741bc`

All were configured with localhost IP whitelist.

## 6. Scheduler situation: built-in schedule vs host cron

### 6.1 Main conclusion

The built-in `Schedule Trigger` in n8n was not accepted as a reliable production mechanism for these MOEX workflows in this environment.

Reason:
- workflows were active;
- expected schedule slots passed;
- no corresponding fresh executions appeared.

### 6.2 Production fallback implemented

A host cron based orchestration layer was prepared and verified.

Files:
- trigger script: `/home/user/n8n-docker/scripts/trigger_moex_workflow.sh`
- cron manifest: `/home/user/n8n-docker/crontab/moex_research.cron`
- installer: `/home/user/n8n-docker/scripts/apply_moex_cron.sh`
- remover: `/home/user/n8n-docker/scripts/remove_moex_cron.sh`
- setup doc: `/home/user/n8n-docker/MOEX_CRON_SETUP.md`

### 6.3 Cron timing details

`moex_research.cron` explicitly sets:
- `CRON_TZ=Europe/Moscow`
- `TZ=Europe/Moscow`

Configured schedules:
- news: every 15 minutes with 3-minute offset (`3,18,33,48 * * * *`)
- candle weekday session windows
- candle weekend session windows
- digest: `00:20 MSK`
- backfill: `03:07 MSK`

### 6.4 Host cron was actually confirmed

The user ran on host:
```bash
cd /home/user/n8n-docker
./scripts/apply_moex_cron.sh
crontab -l
/home/user/n8n-docker/scripts/trigger_moex_workflow.sh news
/home/user/n8n-docker/scripts/trigger_moex_workflow.sh candle
```

Manual webhook trigger outputs on host were successful:
- `news` => `Workflow was started`
- `candle` => `Workflow was started`

Then a real cron slot was observed.

Confirmed host log evidence:
```text
[2026-04-18T08:03:01+03:00] trigger start workflow=news path=moex-news-feed-int-b0e19a6a
[2026-04-18T08:03:01+03:00] trigger success workflow=news target=local response={"message":"Workflow was started"}
```

Therefore:
- host cron orchestration is working;
- the external scheduler fallback is not hypothetical anymore.

## 7. Important observation about n8n execution history

A strange but already non-blocking observation remains:
- successful webhook trigger responses did not consistently appear in `n8n` execution history the way manual executions did;
- `execution_entity` / API views looked incomplete or inconsistent for these webhook-triggered runs.

However, this was explicitly proven to be non-blocking because payload-level verification showed the real data being written and published despite that observability mismatch.

Treat this as an observability oddity, not as a pipeline blocker.

## 8. Payload verification: this is the key factual result

Because direct access to the market research DB from the old sandbox session was not available through the regular Postgres MCP, temporary diagnostic n8n workflows were created and queried through real webhooks using the already-configured credential:
- `Market Research Postgres RW`

Those temporary workflows were deleted afterwards.

### 8.1 Focused payload counts observed

From the focused trade DB probe response:
- `news_item_last_15m = 1176`
- `news_match_last_15m = 0`
- `lightrag_news_item_last_15m = 0`
- `lightrag_candle_snapshot_last_15m = 12`
- `candle_last_15m = 1656`
- `snapshot_last_15m = 24`
- `cursor_last_15m = 12`

Interpretation:
- news raw ingestion is active;
- candle ingestion is active;
- candle snapshots are being published into `tradekb`;
- cursors are being updated;
- zero recent `news_match` / `lightrag_news_item` does not mean failure by itself.

### 8.2 Historical news publish verification

Additional news-focused probe showed:
- `news_item_published_total = 65`
- `news_item_published_last_24h = 65`
- `latest_news_item_published_at = 2026-04-17T18:22:09.521758+00:00`

Last confirmed news publish row:
- `document_type = news_item`
- `source_key = moex/news/GAZP/https_www_moex_com_n98055`
- `source_pk = GAZP:https_www_moex_com_n98055`
- `published_at = 2026-04-17T18:22:09.521758+00:00`

Last confirmed match row:
- `matched_keywords = газпром, газпром`
- `matched_at = 2026-04-17T18:22:08.678007+00:00`

Meaning:
- the news publish path to `tradekb` is working historically;
- the recent zero values only mean no fresh relevant matched news in that window.

### 8.3 Last confirmed candle publish evidence

The focused probe response showed the latest LightRAG publish row was a candle snapshot, for example:
- `target_kb = tradekb`
- `document_type = candle_snapshot`
- `source_key = moex/candles/SBER/1h/2026-04-18T12:00:00.000Z`
- `source_table = analytics.instrument_snapshot`

Meaning:
- candle snapshot publication to the dedicated trade KB is definitely alive.

## 9. Important data-model caveat discovered

### `raw.news_item.ingested_at` semantics

Current SQL in `Upsert Raw News Items` sets `ingested_at = NOW()` even on conflict updates.

So currently:
- `ingested_at` means `last refreshed`, not `first seen`.

This does NOT break downstream deduplication, because publishing uses `RETURNING (xmax = 0) AS inserted`.

But it matters for:
- monitoring,
- analytics,
- interpreting freshness metrics.

Potential future cleanup:
- either accept current semantics;
- or refactor to `first_seen_at + last_seen_at`.

This is not the next critical step.

## 10. Infisical cutover status

### 10.1 What was prepared

A staged cutover was prepared, not yet fully executed.

Files created/updated:
- `/home/user/n8n-docker/docker-compose.yml`
- `/home/user/n8n-docker/.gitignore`
- `/home/user/n8n-docker/.env.infisical.n8n.infra.example`
- `/home/user/n8n-docker/scripts/set_n8n_infra_secrets_in_infisical.sh`
- `/home/user/n8n-docker/scripts/verify_n8n_infra_infisical.sh`
- `/home/user/n8n-docker/INFISICAL_N8N_INFRA_CUTOVER.md`

### 10.2 What changed in docker-compose

Sensitive values were parameterized through env with safe fallback literals still kept for staged migration.

Sensitive variables now parameterized:
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `N8N_ENCRYPTION_KEY`
- `DB_POSTGRESDB_HOST`
- `DB_POSTGRESDB_PORT`
- `DB_POSTGRESDB_DATABASE`
- `DB_POSTGRESDB_USER`
- `DB_POSTGRESDB_PASSWORD`
- `PGADMIN_DEFAULT_EMAIL`
- `PGADMIN_DEFAULT_PASSWORD`
- `POSTGRES_EXPORTER_DATA_SOURCE_NAME`

This is intentional:
- first upload secrets to Infisical;
- then restart;
- only after successful validation remove fallback literals from compose.

### 10.3 Why live cutover was not completed in the old session

The old sandbox session could not access the host keyring/dbus used by Infisical CLI.

Observed error:
```text
failed to fetch credentials from keyring

dial unix /run/user/1000/bus: connect: operation not permitted
```

This means:
- the blocker was the session environment;
- not the Infisical project;
- not the prepared scripts.

### 10.4 Exact host-side cutover steps prepared

Host commands intended for the next stage:

1. create real env file:
```bash
cd /home/user/n8n-docker
cp .env.infisical.n8n.infra.example .env.infisical.n8n.infra
```

2. fill `.env.infisical.n8n.infra` with actual values.

3. upload secrets to Infisical:
```bash
cd /home/user/n8n-docker
./scripts/set_n8n_infra_secrets_in_infisical.sh
```

4. verify all secrets exist:
```bash
cd /home/user/n8n-docker
./scripts/verify_n8n_infra_infisical.sh
```

5. restart stack:
```bash
cd /home/user/n8n-docker
./restart_n8n.sh
```

6. after restart, re-verify:
- n8n is up;
- MOEX workflows remain active;
- host cron still triggers;
- data still lands in trade DB;
- candle snapshots still publish to `tradekb`;
- if possible, re-check a news publish opportunity later.

### 10.5 Remaining cleanup after successful Infisical cutover

Only after successful host-side verification:
1. remove fallback literals from `/home/user/n8n-docker/docker-compose.yml`;
2. ensure plaintext local copies of secret values are no longer needed;
3. decide whether `PGADMIN_DEFAULT_EMAIL` belongs in secret storage or plain config.

## 11. Temporary probe workflows were created and removed

Three temporary workflows were created for diagnostics and later deleted:
- `MOEX | Trade DB Probe Temp`
- `MOEX | Trade DB Focus Probe Temp`
- `MOEX | News Publish Probe Temp`

They should not exist anymore.

## 12. Files that matter most right now

### Main operational files
- `/home/user/n8n-docker/docker-compose.yml`
- `/home/user/n8n-docker/restart_n8n.sh`
- `/home/user/n8n-docker/run-n8n.sh`
- `/home/user/n8n-docker/start-n8n.sh`

### Cron files
- `/home/user/n8n-docker/crontab/moex_research.cron`
- `/home/user/n8n-docker/scripts/trigger_moex_workflow.sh`
- `/home/user/n8n-docker/scripts/apply_moex_cron.sh`
- `/home/user/n8n-docker/scripts/remove_moex_cron.sh`
- `/home/user/n8n-docker/MOEX_CRON_SETUP.md`

### Infisical files
- `/home/user/n8n-docker/.infisical.json`
- `/home/user/n8n-docker/.env.infisical.n8n.infra.example`
- `/home/user/n8n-docker/scripts/set_n8n_infra_secrets_in_infisical.sh`
- `/home/user/n8n-docker/scripts/verify_n8n_infra_infisical.sh`
- `/home/user/n8n-docker/INFISICAL_N8N_INFRA_CUTOVER.md`

### Existing rolling handoff log from the old session
- `/home/user/trade-kb-handoff-2026-04-18.md`

This file contains the chronological trail of intermediate findings and should also be read by the next session.

## 13. Exact recommended first actions for the next session

The next session should do this in order:

1. Read this file:
- `/home/user/codex-restart-handoff-2026-04-18.md`

2. Read the rolling handoff log:
- `/home/user/trade-kb-handoff-2026-04-18.md`

3. Confirm the new Codex session really has full access:
- test whether `sudo` now works normally;
- test whether docker and Infisical keyring access are available.

4. If full access works, perform the Infisical cutover directly on host:
- fill `.env.infisical.n8n.infra`
- run upload script
- run verify script
- restart n8n stack

5. After restart, do post-cutover verification:
- verify n8n availability;
- verify MOEX workflow activation;
- verify host cron logs still update;
- verify payload-level writes still happen;
- verify `tradekb` still receives candle snapshots.

6. Only after successful verification, remove compose fallback literals.

## 14. What should NOT be re-investigated from scratch

The next session should not waste time re-proving these already established points:

- separate trade KB concept is correct;
- host cron fallback is working;
- candle ingestion and candle publish are working;
- news raw ingestion is working;
- news publish path to `tradekb` is historically working;
- the old session’s main blocker was sandbox/keyring access, not broken business logic.

## 15. Short executive summary for the next session

Current state at restart:
- infrastructure is mostly ready;
- trade DB and `tradekb` are alive;
- cron fallback works;
- the remaining meaningful task is to complete the Infisical migration on the host and then clean up the remaining plaintext fallbacks.

If the restarted Codex session has real full access, the right move is not more analysis.
The right move is to execute the Infisical cutover and verify the stack.

## 16. Update 2026-04-18 14:45 MSK

The host-side Infisical cutover has now been executed.

Completed:

- `lightrag-trade` runtime variables were uploaded to `Infisical` path `/lightrag-trade`
- `lightrag-trade` now starts via `/home/user/lightrag-trade/scripts/compose_with_infisical.sh`
- local plaintext `/home/user/lightrag-trade/.env` was removed
- `n8n-docker` infra secrets were uploaded/verified in `Infisical`
- `/home/user/n8n-docker/docker-compose.yml` no longer contains sensitive fallback literals
- `/home/user/n8n-docker/scripts/compose_with_infisical.sh` was added
- `/home/user/n8n-docker/restart_n8n.sh` now uses the compose wrapper
- the `n8n-docker` stack was recreated successfully via `infisical run -- docker compose up -d`
- verification:
  - `https://bigalexn8n.ru` returned `200`
  - `http://127.0.0.1:9623/health` returned `healthy`
  - `docker compose ps` through both wrappers showed the expected running services

What is no longer the blocker:

- Infisical/keyring access is now working well enough for operational use in this host-access session
- the remaining work is no longer secret migration

The next useful priorities are back to product/infrastructure behavior:

1. activate only the workflows that should truly run in production
2. verify cron-driven executions keep writing to trade DB after the stack restarts
3. decide whether any additional cleanup is needed around old unused secret names in the root `dev` environment
