# Trade System Technical Review
_Date: 2026-04-19_

## Scope

This review covers the current MOEX virtual trader stack:

- `/home/user/run_ai_trading.sh`
- `/home/user/ai_trader_daemon.py`
- `/home/user/ai_paper_trader.py`
- `/home/user/ai_hourly_report.py`
- `/home/user/ai_daily_report.py`
- `/home/user/ai_trader_daemon.sh` as legacy artifact
- `/home/user/TRADE_SYSTEM_HANDOFF.md`
- `/home/user/BOT_TRADING_STRATEGY.md`
- `/home/user/n8n-docker/migrations/003_trading_schema.sql`
- `/home/user/n8n-docker/migrations/004_multiagent_trading.sql`

## Executive Summary

The system is currently a hybrid of two different implementations:

1. The documentation and database schema describe a full paper-trading engine with position updates, journal writes, daily statistics, and agent learning.
2. The current runtime code behaves mostly like an AI analysis and reporting system. It reads market and portfolio state, asks Gemini for analysis, and sends Telegram messages, but it does not currently execute or persist trade decisions.

That mismatch is the main architectural problem. The system name and docs imply an autonomous trading league, but the active runtime no longer closes the loop.

## Current Runtime Architecture

### Entry Points

- `run_ai_trading.sh` is the shell wrapper and secret bootstrapper.
- `run_ai_trading.sh daemon` starts `ai_trader_daemon.py`.
- `run_ai_trading.sh trade <name>` starts `ai_paper_trader.py <name>`.
- `run_ai_trading.sh hourly` starts `ai_hourly_report.py`.
- `run_ai_trading.sh report` starts `ai_daily_report.py`.

Reference:

- `run_ai_trading.sh:14-27`

### Runtime Flow

```text
nohup / cron / manual start
    ->
run_ai_trading.sh daemon
    ->
ai_trader_daemon.py
    ->
for each trader in TRADERS:
    run_ai_trading.sh trade <trader>
        ->
    ai_paper_trader.py
        ->
    read DB state
        ->
    call Gemini CLI
        ->
    send Telegram summary

hourly branch:
    ai_hourly_report.py
        ->
    read DB state
        ->
    build matplotlib chart
        ->
    send Telegram photo

daily branch:
    ai_daily_report.py
        ->
    read journal and portfolio
        ->
    call Gemini for lessons
        ->
    update trader_config.learned_traits
        ->
    send Telegram text report
```

### Core Components

#### 1. Wrapper and Secrets

`run_ai_trading.sh` loads secrets from Infisical and dispatches one of four subcommands.

Strengths:

- central place for process start
- one place for secret bootstrap

Weaknesses:

- no argument validation for `trade`
- no lock file or PID file
- shell wrapper and Python layers both own runtime behavior

Reference:

- `run_ai_trading.sh:8-27`

#### 2. Daemon / Scheduler

`ai_trader_daemon.py` is the real orchestrator. It contains the list of 10 traders and spawns one background process per trader with a 3-second delay between launches, then sleeps 20 seconds before another loop.

Reference:

- `ai_trader_daemon.py:10-14`
- `ai_trader_daemon.py:25-52`

#### 3. Trader Engine

`ai_paper_trader.py` currently does three things:

- reads market, portfolio, and trader traits from PostgreSQL
- builds a prompt and calls Gemini with fallback across ranked models
- sends a human-readable Telegram report

It currently does not:

- validate actions against risk rules
- apply trades to `trading.portfolio` and `trading.position`
- insert executed decisions into `trading.journal`
- persist `raw` or normalized AI decisions

Reference:

- DB reads: `ai_paper_trader.py:378-388`
- prompt building: `ai_paper_trader.py:389-402`
- model fallback: `ai_paper_trader.py:328-372`
- current terminal behavior: `ai_paper_trader.py:403-408`

#### 4. Hourly Report

`ai_hourly_report.py` computes current equity per trader and generates a chart. It uses the latest `trading.daily_stats.total_value` as the baseline. If that table is empty, it silently falls back to `10000.0`.

Reference:

- baseline logic: `ai_hourly_report.py:82-87`

#### 5. Daily Report / Learning Loop

`ai_daily_report.py` is responsible for generating short mentor feedback and storing it into `trading.trader_config.learned_traits`.

Reference:

- Gemini lesson generation: `ai_daily_report.py:30-54`
- trait update: `ai_daily_report.py:50-52`

### Data Model Actually Used by Runtime

Runtime reads or writes these tables:

- `trading.portfolio`
- `trading.position`
- `trading.journal`
- `trading.daily_stats`
- `trading.trader_config`

Observed DB state on 2026-04-19:

- `trading.portfolio`: 10 rows
- `trading.position`: 50 rows
- `trading.journal`: 122 rows
- `trading.daily_stats`: 0 rows
- `trading.trader_config`: 10 rows

Important note:

`trading.trader_config` is used by runtime, but it is not defined in the two checked migration files under `n8n-docker/migrations`. That indicates schema drift between runtime and migration history.

## Intended Architecture vs Actual Architecture

### Intended

```text
market snapshot + trader memory + RAG
    ->
AI decision
    ->
risk validation
    ->
portfolio/position/journal updates
    ->
hourly and daily reporting
    ->
daily learning feedback
```

### Actual

```text
market snapshot + trader memory
    ->
AI decision
    ->
human-readable Telegram summary

historical positions and journal remain mostly from older runs
```

This is the central mismatch in the system.

## Review Findings

### High Severity

#### 1. The trader runtime no longer executes or persists decisions

`ai_paper_trader.py` reads state, calls the model, and sends a report, but does not apply any trade or write journal entries. The main path ends at:

- `ai_paper_trader.py:403-408`

Impact:

- the system is not a paper-trading engine anymore
- daemon activity does not necessarily change portfolio state
- Telegram can look healthy while trading state remains stale
- historical `trading.journal` rows can mislead users into thinking the current engine still writes trades

#### 2. RAG access is described in the prompt but not guaranteed by the Gemini CLI invocation

`ai_paper_trader.py` instructs the model to query `lightrag-algo`, but the CLI command does not include `--allowed-mcp-server-names`.

References:

- prompt requires RAG: `ai_paper_trader.py:394-400`
- CLI call omits MCP allowlist: `ai_paper_trader.py:331-333`
- daily report includes allowlist: `ai_daily_report.py:44`
- helper fix file includes allowlist: `/home/user/ai_call_fix.py:4`

Impact:

- the trader may operate without the knowledge base even when the prompt says otherwise
- behavior is environment-dependent and non-deterministic
- debugging model quality becomes very difficult

#### 3. The daemon launches overlapping trader runs without real concurrency control

The comment says "не более 3-х одновременно", but the code does not enforce that. It uses `subprocess.Popen(...)` for every trader, waits 3 seconds between launches, then starts another round after a fixed 20-second sleep.

Reference:

- `ai_trader_daemon.py:30-36`
- `ai_trader_daemon.py:51-52`

Impact:

- overlapping runs can pile up when Gemini is slow
- quota burn becomes aggressive
- if trade execution is restored later, race conditions will corrupt positions and journal
- logs become misleading because "Tick" does not mean completion

#### 4. `daily_stats` is effectively dead, but hourly reporting depends on it

`ai_hourly_report.py` uses `trading.daily_stats` as its baseline source. `ai_daily_report.py` never inserts into `trading.daily_stats`, and the current database shows zero rows in that table.

References:

- hourly baseline read: `ai_hourly_report.py:82-87`
- daily report has no insert into `trading.daily_stats`: `ai_daily_report.py:56-80`

Impact:

- hourly PnL is measured against a hardcoded fallback, not a real start-of-day baseline
- report numbers become misleading after the first day
- long-term equity tracking is broken

### Medium Severity

#### 5. Legacy shell daemon is broken and dangerous as an alternate entry point

`ai_trader_daemon.sh` calls:

- `bash /home/user/run_ai_trading.sh trade`

but the wrapper expects:

- `trade <name>`

and `ai_paper_trader.py` exits immediately if the trader name is missing.

References:

- broken legacy call: `ai_trader_daemon.sh:11-12`
- wrapper contract: `run_ai_trading.sh:15-17`
- runtime guard: `ai_paper_trader.py:375-376`

Impact:

- anyone starting the legacy daemon gets a silently broken system
- documentation and operations become error-prone

#### 6. Configuration is hardcoded across multiple scripts

Hardcoded values include:

- DB credentials
- Telegram chat ID
- log paths
- proxy address
- Infisical project ID

References:

- `ai_paper_trader.py:6-10`
- `ai_hourly_report.py:9-20`
- `ai_daily_report.py:8-16`
- `run_ai_trading.sh:3-10`

Impact:

- environment portability is poor
- secret rotation requires code changes
- production and test environments cannot be separated cleanly

#### 7. Notification failure handling is inconsistent and often silent

Examples:

- `ai_paper_trader.py` prints Telegram errors to stdout only
- `ai_daily_report.py` suppresses exceptions with bare `except: pass`

References:

- `ai_paper_trader.py:55-64`
- `ai_daily_report.py:18-25`
- `ai_daily_report.py:45-54`

Impact:

- operators may believe the system is healthy when notifications are failing
- delivery failures are not visible in unified logs

#### 8. Runtime assumes rows always exist in DB

`ai_paper_trader.py` uses `cur.fetchone()[0]` for portfolio and trader traits without guard rails.

References:

- `ai_paper_trader.py:380-382`

Impact:

- any missing `portfolio` or `trader_config` row causes a runtime exception
- onboarding a new trader is fragile

#### 9. Migration history does not match the live system

`004_multiagent_trading.sql` initializes only three traders, while runtime expects ten traders.

Reference:

- `004_multiagent_trading.sql:20-24`
- runtime list: `ai_trader_daemon.py:10-14`

Impact:

- a clean rebuild from migrations does not reproduce the current runtime contract
- this is a deployment risk and a maintainability problem

### Low Severity

#### 10. Strategy and handoff docs overstate current functionality

`TRADE_SYSTEM_HANDOFF.md` describes a full trading loop with journal writes and active learning, but current runtime behavior is narrower.

Reference:

- `TRADE_SYSTEM_HANDOFF.md:7-36`

Impact:

- new operators will assume more automation than actually exists
- debugging starts from the wrong mental model

## Recommended Target Architecture

### Layered Design

```text
Scheduler Layer
    systemd timer / controlled queue / single orchestrator

Orchestration Layer
    dispatch trader runs
    guarantee no overlap
    capture run IDs and status

Decision Layer
    build prompt
    call AI with fallback
    normalize output
    persist raw response

Execution Layer
    validate risk rules
    apply trades transactionally
    write journal and portfolio updates

Reporting Layer
    hourly standings
    end-of-day summary
    daily_stats snapshots

Learning Layer
    derive lessons from journal and performance
    update trader memory
```

## Improvement Plan

### Phase 0. Clarify System Mode

Goal:

- make the system honest about what it currently does

Tasks:

- decide whether the current system is "analysis-only" or "paper-trading"
- if analysis-only, rename scripts and docs accordingly
- if paper-trading, restore execution path before any further feature work
- delete or archive `ai_trader_daemon.sh`

### Phase 1. Stabilize the Orchestrator

Goal:

- stop overlapping runs and make scheduling deterministic

Tasks:

- replace open-ended `Popen` fan-out with a bounded worker pool or serial scheduler
- add PID lock or run lock
- add per-run UUID and structured log entries
- record start, success, failure, model used, duration
- replace `nohup` launch practice with a `systemd` service if this is a host-level daemon

### Phase 2. Restore the Trading Loop

Goal:

- close the loop from AI decision to persisted state

Tasks:

- define a strict decision schema
- persist raw AI response before execution
- normalize actions into `BUY`, `SELL`, `HOLD`, `WATCH`
- add validation rules:
  - ticker exists
  - quantity is integer and positive
  - cannot sell more than held
  - cannot buy above cash limit
  - per-position allocation cap
- apply portfolio and position updates in one DB transaction
- insert journal records for every executed action
- store non-executed AI suggestions separately from executed trades

### Phase 3. Repair Reporting

Goal:

- make PnL and leaderboards trustworthy

Tasks:

- write `trading.daily_stats` every day, per trader
- optionally also write intraday snapshots into a separate table
- use real start-of-day baseline in hourly report
- show model used and run status in reports
- separate "analysis completed" from "trade executed"

### Phase 4. Unify Configuration

Goal:

- remove environment drift and secret sprawl

Tasks:

- move DB config, Telegram config, proxy config, and paths into environment variables
- load them through a shared config module
- fail fast if required configuration is missing
- avoid reading `.env` ad hoc in multiple files

### Phase 5. Add Observability and Tests

Goal:

- make the system debuggable and safe to change

Tasks:

- add unit tests for prompt normalization and fallback logic
- add integration tests for trade execution and position accounting
- add smoke tests for each entry point
- add a dry-run mode for trader execution
- log to structured JSON or at least consistent text with trader name, model, run ID, and stage

### Phase 6. Fix Schema Drift

Goal:

- make a clean deploy reproducible

Tasks:

- add explicit migration for `trading.trader_config`
- add migration that inserts all 10 traders
- reconcile old single-agent schema with current multi-agent runtime
- document required DB invariants

## Suggested Immediate Backlog

### Priority 1

- Restore explicit RAG access in `ai_paper_trader.py`
- Remove or disable `ai_trader_daemon.sh`
- Add a run lock to the daemon
- Write `daily_stats`
- Decide whether to restore actual trade execution now or mark the system as analysis-only

### Priority 2

- Refactor shared config and Telegram helper
- Persist raw AI decisions
- Add run metadata and structured logging

### Priority 3

- Move daemon start from `nohup` to `systemd`
- Add tests and dry-run mode
- Improve reporting UX

## Recommended Next Step

The next engineering step should be one of these two explicit choices:

1. Restore the real paper-trading engine by reintroducing transactional trade execution and journal writes into `ai_paper_trader.py`.
2. Freeze the current runtime as an analysis-only league, rename the scripts and docs, and stop claiming autonomous paper trading.

Until that choice is made, the system will continue to look more autonomous than it really is.
