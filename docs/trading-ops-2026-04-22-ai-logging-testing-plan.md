# Trading Ops: AI Input/Output Logging And Script Testing Plan

Date: 2026-04-22
Purpose: temporary deep logging and repeatable tests for tuning AI input data without silently breaking trading scripts.

## Goals

1. Verify every AI-related script can run.
2. Verify every script produces the expected type of output.
3. Log exactly what is sent into AI and what comes back.
4. Measure freshness and volume of input data before each AI call.
5. Keep this logging temporary, bounded, and easy to disable.
6. Avoid spending Gemini quota during tests unless an explicit real-AI smoke test is requested.

## Current Baseline

Already implemented:

- central AI runner in `gemini_cli_runner.py`;
- cost/accounting table `trading.ai_call_log`;
- prompt length, estimated tokens, response length, status, model, duration;
- prompt budget and hourly budget;
- fallback caps and model health skip;
- several dry/test modes:
  - `AI_TEST_MODE=1` for nightly/report scripts;
  - `AI_SENTIMENT_DRY_RUN=1` for sentiment;
  - `ai_backtester.py` dry-run by default;
  - fake `GEMINI_BIN` can test the runner without spending Gemini calls.

Current gap:

- `trading.ai_call_log` stores metrics but not the full prompt/response.
- Callers do not pass structured metadata about source freshness/volume.
- Tests are manual commands, not one repeatable suite with expected results.

## Temporary Deep AI I/O Logging

### Principle

The tuning log must answer four questions for every AI call:

1. What exact prompt did the model receive?
2. What exact response did it return?
3. How fresh was each input source?
4. How large was each input source and prompt section?

### Enablement

Use an explicit environment flag:

```bash
AI_DEBUG_IO_LOG=1
```

Default must stay off.

Optional flags:

```bash
AI_DEBUG_IO_RETENTION_DAYS=7
AI_DEBUG_IO_MAX_PROMPT_CHARS=200000
AI_DEBUG_IO_MAX_RESPONSE_CHARS=200000
AI_DEBUG_IO_SAMPLE_RATE=1.0
AI_DEBUG_IO_REDACT_SECRETS=1
```

### Storage

Add a table:

```sql
CREATE TABLE IF NOT EXISTS trading.ai_io_debug_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    ai_call_log_id BIGINT REFERENCES trading.ai_call_log(id) ON DELETE SET NULL,
    script_name TEXT,
    call_name TEXT,
    trader_name TEXT,
    category TEXT NOT NULL,
    model_id TEXT,
    status TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    response_sha256 TEXT,
    prompt_chars INTEGER NOT NULL,
    response_chars INTEGER NOT NULL DEFAULT 0,
    prompt_text TEXT,
    response_text TEXT,
    input_freshness JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_volume JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_io_debug_log_created_idx
    ON trading.ai_io_debug_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_io_debug_log_category_created_idx
    ON trading.ai_io_debug_log (category, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_io_debug_log_call_idx
    ON trading.ai_io_debug_log (call_name, created_at DESC);
```

### Redaction

Before writing full prompt/response, redact:

- Telegram bot tokens;
- passwords;
- Infisical tokens;
- DB passwords;
- URLs with credentials;
- auth headers;
- API keys.

Even if prompts should not contain secrets, the logger should not trust callers.

### Retention

Add cleanup:

```sql
DELETE FROM trading.ai_io_debug_log
WHERE expires_at < now();
```

Schedule once per day or include in existing maintenance.

### Runner Integration

Update `gemini_cli_runner.py`:

- add optional parameter `input_meta=None`;
- pass it to the debug logger;
- on preflight block, log the prompt with status `budget_blocked`;
- on success, log prompt + response;
- on parse error, log prompt + raw response;
- on timeout/error/exhausted, log prompt + stderr/stdout snippet as response/error context.

Keep `trading.ai_call_log` as the lightweight always-on table. `ai_io_debug_log` is temporary heavy logging.

## Structured Input Metadata

### Common Shape

Every AI caller should pass:

```json
{
  "input_freshness": {
    "market_context_max_age_seconds": 120,
    "kb_context_age_seconds": 900,
    "positions_age_seconds": 5,
    "journal_lookback_hours": 24
  },
  "input_volume": {
    "market_symbols": 21,
    "market_payload_chars": 1400,
    "positions": 3,
    "history_items": 3,
    "kb_chars": 900,
    "prompt_chars": 3200
  },
  "prompt_sections": {
    "system_chars": 240,
    "kb_chars": 900,
    "portfolio_chars": 180,
    "market_chars": 1400,
    "instructions_chars": 420
  },
  "validation_warnings": []
}
```

### Required Warnings

Add warning strings when:

- market context is empty;
- market context age is above threshold;
- KB context is low-quality or missing;
- prompt exceeds target size but is below hard budget;
- response has no actions;
- response contains unknown symbols;
- response contains unsupported actions;
- response JSON parses but schema is incomplete;
- sentiment is stale;
- backtest day payload has too few symbols.

### Script-Specific Metadata

`ai_paper_trader.py`:

- market symbols count;
- max/min `updated_at`;
- market context age;
- KB cache hit/miss and KB quality;
- positions count;
- journal history count;
- prompt section sizes;
- output actions count and invalid actions count.

`ai_crypto_trader.py`:

- same as MOEX, plus exchange data age by symbol/window.

`ai_sentiment_oracle.py`:

- tickers due;
- tickers skipped as fresh;
- sentiment freshness threshold;
- prompt chars per ticker batch;
- returned items count;
- missing ticker count.

`ai_daily_report.py` / `ai_crypto_daily_report.py`:

- traders analyzed;
- trades per trader;
- positions per trader;
- failed/fallback lesson count;
- quality gate result;
- KB upload allowed/skipped.

`ai_evolution.py`:

- market groups count;
- raw row count before compression;
- prompt chars after compression;
- trader trade summaries count;
- analysis window hours/days;
- report quality result.

`ai_genetic_incubator.py`:

- assets count;
- raw rows count;
- compressed payload chars;
- selected top assets;
- report quality result.

`ai_watchdog_analyzer.py`:

- log files scanned;
- lines scanned;
- errors/timeouts/quota counts;
- prompt chars;
- report quality result.

`ai_backtester.py`:

- symbols;
- days;
- batch days;
- prompt chars per batch;
- valid dates;
- skipped dates;
- AI calls;
- simulated trades;
- final equity.

## Testing Strategy

### Test Levels

1. Static tests:
   - Python compile;
   - shell syntax;
   - `git diff --check`.

2. Schema tests:
   - create/upgrade logging tables;
   - verify indexes;
   - insert one synthetic debug record;
   - cleanup expired records.

3. Runner tests without Gemini:
   - fake Gemini returns valid JSON;
   - fake Gemini returns invalid JSON;
   - fake Gemini simulates capacity error;
   - prompt hard budget blocks call;
   - fallback cap stops after expected attempts;
   - model health skip works.

4. Script smoke tests without Gemini spend:
   - use `AI_TEST_MODE=1`, dry-run flags, or fake `GEMINI_BIN`;
   - verify exit code;
   - verify expected DB/log side effects;
   - verify no Telegram/KB upload in test mode.

5. Expected-output tests:
   - assert that each script returns or writes the expected shape.

6. One controlled real-AI smoke:
   - optional;
   - only after fake tests pass;
   - one small script, one small prompt, one model attempt.

## Expected Script Results

### `ai_paper_trader.py`

Smoke mode needed:

```bash
AI_TRADER_DRY_RUN=1
GEMINI_BIN=/home/user/tmp/fake_gemini_cli.py
/home/user/trading_venv/bin/python /home/user/ai_paper_trader.py Chaos_Bill
```

Expected:

- exit code `0` if market context and fake AI response are valid;
- no real journal insert when `AI_TRADER_DRY_RUN=1`;
- `trading.ai_call_log` row with category `trader`;
- `trading.ai_io_debug_log` row when `AI_DEBUG_IO_LOG=1`;
- prompt metadata shows non-empty `market_symbols`.

Need to implement `AI_TRADER_DRY_RUN=1`; current script does not have it.

### `ai_crypto_trader.py`

Same as MOEX, but crypto is currently paused.

Expected:

- exit code `0` in dry-run with fake AI if crypto context exists;
- no DB mutation under dry-run;
- no live scheduling until crypto is explicitly re-enabled.

Need to implement `AI_TRADER_DRY_RUN=1` here too.

### `ai_sentiment_oracle.py`

Command:

```bash
AI_SENTIMENT_DRY_RUN=1
AI_SENTIMENT_FORCE=1
AI_SENTIMENT_MAX_TICKERS=3
/home/user/trading_venv/bin/python /home/user/ai_sentiment_oracle.py
```

Expected:

- exit code `0`;
- log says it would update 3 tickers in one batch;
- no Gemini call;
- no DB updates.

### `ai_daily_report.py`

Command:

```bash
AI_TEST_MODE=1
AI_DAILY_REPORT_MAX_TRADERS=2
GEMINI_BIN=/home/user/tmp/fake_gemini_cli.py
/home/user/trading_venv/bin/python /home/user/ai_daily_report.py
```

Expected:

- exit code `0`;
- no Telegram send;
- no ALGO KB upload;
- chart generation succeeds;
- quality gate passes if fake response contains both traders;
- debug log stores batch prompt/response if enabled.

Need fake response generator aware of requested call name.

### `ai_crypto_daily_report.py`

Run only while crypto is paused as test mode/dry run.

Expected:

- one batch AI call under fake Gemini;
- no low-quality per-trader KB uploads;
- no Telegram if test mode is added.

Need to add `AI_TEST_MODE=1` support to crypto daily report.

### `ai_evolution.py`

Command:

```bash
AI_TEST_MODE=1
GEMINI_BIN=/home/user/tmp/fake_gemini_cli.py
/home/user/trading_venv/bin/python /home/user/ai_evolution.py
```

Expected:

- exit code `0`;
- synthetic payload;
- no Telegram;
- no KB upload;
- prompt chars under category limit.

### `ai_genetic_incubator.py`

Same pattern as evolution.

Expected:

- exit code `0`;
- no KB upload in test mode;
- prompt chars under category limit.

### `ai_watchdog_analyzer.py`

Command:

```bash
AI_TEST_MODE=1
GEMINI_BIN=/home/user/tmp/fake_gemini_cli.py
/home/user/trading_venv/bin/python /home/user/ai_watchdog_analyzer.py
```

Expected:

- exit code `0`;
- no KB upload in test mode;
- debug metadata includes log file/error summary.

### `ai_backtester.py`

Dry run:

```bash
/home/user/trading_venv/bin/python /home/user/ai_backtester.py \
  --start 2026-04-15 --end 2026-04-21 \
  --trader Chaos_Bill \
  --max-days 3 --max-symbols 5 --batch-days 2
```

Expected:

- exit code `0`;
- `execute_ai=false`;
- `ai_calls=0`;
- `days=3`;
- symbols non-empty;
- final equity unchanged.

Fake AI:

```bash
GEMINI_BIN=/home/user/tmp/fake_gemini_cli.py
/home/user/trading_venv/bin/python /home/user/ai_backtester.py \
  --start 2026-04-15 --end 2026-04-15 \
  --trader Chaos_Bill \
  --max-days 1 --max-symbols 2 --batch-days 1 \
  --execute-ai
```

Expected:

- exit code `0`;
- `ai_calls=1`;
- simulated trade if fake response contains a valid action;
- debug log row if enabled.

## Test Harness

Add:

```text
tests/
  fake_gemini_cli.py
  run_ai_smoke_tests.sh
  expected/
```

`fake_gemini_cli.py` behavior:

- detect `--output-format`;
- detect prompt content/call type where possible;
- return valid JSON for trader/backtester/daily/sentiment;
- support env modes:
  - `FAKE_GEMINI_MODE=valid`;
  - `FAKE_GEMINI_MODE=invalid_json`;
  - `FAKE_GEMINI_MODE=capacity`;
  - `FAKE_GEMINI_MODE=slow`.

`run_ai_smoke_tests.sh`:

- exports `GEMINI_BIN=/home/user/tests/fake_gemini_cli.py`;
- exports `AI_DEBUG_IO_LOG=1`;
- runs static/schema/runner/script tests;
- prints a compact pass/fail table;
- exits non-zero on failure.

## Implementation Order

### Step 1: Deep Logger Module

Create `ai_io_debug_logger.py`:

- DDL for `trading.ai_io_debug_log`;
- redaction;
- sha256;
- size caps;
- retention;
- `log_debug_io(...)`;
- `cleanup_debug_logs(...)`.

Tests:

- create schema;
- insert synthetic prompt/response;
- verify redaction;
- verify cleanup.

### Step 2: Runner Integration

Update `gemini_cli_runner.py`:

- add `input_meta=None`;
- log prompt/response on all statuses when `AI_DEBUG_IO_LOG=1`;
- return or internally preserve `ai_call_log_id` if practical.

Tests:

- fake valid JSON logs prompt and response;
- fake invalid JSON logs raw response;
- budget block logs prompt and no response;
- redaction works.

### Step 3: Caller Metadata

Add metadata builders to:

- `ai_paper_trader.py`;
- `ai_crypto_trader.py`;
- `ai_sentiment_oracle.py`;
- `ai_daily_report.py`;
- `ai_crypto_daily_report.py`;
- `ai_evolution.py`;
- `ai_genetic_incubator.py`;
- `ai_watchdog_analyzer.py`;
- `ai_backtester.py`.

Tests:

- debug log has non-empty `input_volume`;
- debug log has expected freshness keys;
- warnings are emitted for intentionally empty/stale inputs.

### Step 4: Dry-Run Safety

Add missing dry-run flags:

- `AI_TRADER_DRY_RUN=1` to trader scripts;
- `AI_TEST_MODE=1` to crypto daily report;
- optional `AI_MATCHING_DRY_RUN=1` to matching engine before testing execution changes.

Tests:

- scripts can run without mutating journal/portfolio/KB/Telegram.

### Step 5: Smoke Test Suite

Create `tests/run_ai_smoke_tests.sh`.

Minimum checks:

- `py_compile`;
- shell syntax;
- schema creation;
- runner fake-valid/fake-invalid/fake-capacity/fake-budget;
- sentiment dry-run;
- daily report test mode;
- evolution/incubator/watchdog test mode;
- backtester dry-run and fake AI;
- trader dry-run and fake AI.

### Step 6: Expected Result Assertions

Do not only check exit code. Assert:

- `trading.ai_call_log` row count increased as expected;
- `trading.ai_io_debug_log` row exists when enabled;
- prompt chars under target;
- input metadata includes counts/freshness;
- response parsed or parse failure recorded;
- no external side effects in test mode.

### Step 7: Temporary Tuning Window

Run deep logging only during tuning:

- 1-3 trading sessions for MOEX;
- only with traders enabled under guarded dispatcher;
- crypto remains paused;
- daily cleanup of old debug logs;
- after tuning, set `AI_DEBUG_IO_LOG=0`.

## Acceptance Criteria

The logging/testing work is done when:

1. Every AI call can be traced from script to model to prompt to response.
2. Every prompt has freshness/volume metadata.
3. There is a one-command smoke test suite.
4. Tests do not spend Gemini quota by default.
5. Test mode does not mutate trading state unintentionally.
6. Debug logs are redacted and expire automatically.
7. We can identify bloated/stale/empty context from SQL without reading raw logs manually.

## Useful Diagnostic Queries

Recent prompt sizes:

```sql
SELECT category, call_name, trader_name, status, prompt_chars, response_chars, created_at
FROM trading.ai_io_debug_log
ORDER BY created_at DESC
LIMIT 50;
```

Largest prompt sections:

```sql
SELECT
  id,
  category,
  call_name,
  prompt_sections,
  input_volume,
  created_at
FROM trading.ai_io_debug_log
ORDER BY prompt_chars DESC
LIMIT 20;
```

Stale inputs:

```sql
SELECT id, category, call_name, input_freshness, validation_warnings, created_at
FROM trading.ai_io_debug_log
WHERE jsonb_array_length(validation_warnings) > 0
ORDER BY created_at DESC
LIMIT 50;
```

Low-quality responses:

```sql
SELECT id, category, call_name, status, response_chars, validation_warnings, created_at
FROM trading.ai_io_debug_log
WHERE status IN ('parse_error', 'error', 'budget_blocked')
   OR response_chars < 40
ORDER BY created_at DESC
LIMIT 50;
```
