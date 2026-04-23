# Trading Ops 2026-04-22: Trader Prompt Log Analysis

## What Was Analyzed

Source:

- `trading.ai_io_debug_log`
- category: `trader`
- window: last 24 hours on 2026-04-22

Analyzer added:

- `/home/user/ai_prompt_log_analyzer.py`

Usage:

```bash
/home/user/ai_prompt_log_analyzer.py --hours 24
/home/user/ai_prompt_log_analyzer.py --hours 6 --json
```

## Findings

Observed rows:

- 67 trader debug rows;
- statuses: `budget_blocked=5`, `timeout=10`, `exhausted=16`, `model_skipped=33`, `parse_error=3`;
- prompt average: about 4.6k chars;
- prompt p90: about 6.5k chars;
- max prompt: about 6.6k chars;
- response chars: 0 in these rows because the sampled calls failed or were blocked/skipped.

Prompt section sizes:

- `MARKET_FEATURES`: avg about 2.7k chars, max about 3.8k;
- `KB`: avg about 1.1k chars, max about 3.4k;
- `DNA`, portfolio, regime, history, cash and output instruction are small.

Market data quality:

- every parsed prompt had 12 symbols;
- market feature JSON parsed successfully;
- market data age averaged about 158 seconds;
- max observed age was 480 seconds.

KB quality issue:

- 23 of 67 rows had generic KB content;
- examples were generic educational text about strategic alpha/risk, not actionable stored trading context;
- KB query used the first 5 symbols from the broader price snapshot, not the exact symbols selected for `MARKET_FEATURES`.

Old debug-log bloat:

- 33 old `model_skipped` rows stored the full prompt;
- this was already fixed in `ai_cost_guard.py`: future `model_skipped` rows store an empty prompt.

## Changes Made

### KB Query

Updated `/home/user/ai_paper_trader.py`:

- KB query now uses the actual selected `MARKET_FEATURES` symbols;
- query asks for compact actionable lessons/risk flags only;
- query explicitly rejects generic definitions and generic finance theory;
- `compact_kb_context()` rejects known generic KB patterns;
- KB context is capped by `AI_TRADER_KB_MAX_CHARS`, default `1200`;
- number of symbols in KB query is tunable by `AI_TRADER_KB_SYMBOLS`, default `6`.

### Symbol Selection

Updated `/home/user/trading_feature_contract.py`:

- symbol selection now mixes movement and liquidity;
- fast/action traders get more movement-ranked symbols;
- slow/value/index traders keep stronger liquidity coverage;
- this avoids losing fast movers purely because daily value was lower.

Example after change:

- `Scalper_Kesha` selected `CHMF`, `MAGN`, `NLMK`, `MTSS`, `TATN`, `OZON`, plus liquid names like `VTBR`, `SBER`, `GAZP`;
- feature payload stayed compact, about 3k chars for 12 symbols.

### Runtime Tunables

Updated `/home/user/run_ai_trader_once.sh`:

- `AI_TRADER_KB_MAX_CHARS=1200`
- `AI_TRADER_KB_SYMBOLS=6`

Existing useful tunable:

- `AI_TRADER_MAX_SYMBOLS=12`

## Verification

Passed:

```bash
/home/user/trading_venv/bin/python -m py_compile \
  /home/user/ai_paper_trader.py \
  /home/user/trading_feature_contract.py \
  /home/user/ai_prompt_log_analyzer.py \
  /home/user/ai_cost_guard.py \
  /home/user/gemini_cli_runner.py

bash -n /home/user/run_ai_trader_once.sh
/home/user/ai_prompt_log_analyzer.py --hours 24
/home/user/tests/run_tuning_phase1_phase2_smoke.sh
```

Additional dry-run:

- ran `Scalper_Kesha` with fake Gemini and debug logging;
- new prompt did not contain generic strategic-alpha KB text;
- prompt contained actionable compact KB bullets;
- test rows from `ai_call_log` / `ai_io_debug_log` were cleaned up.

## Current Assessment

The prompt is no longer catastrophically large. The largest remaining input is the market feature payload, which is expected and mostly useful. The main quality/cost issue was KB noise, now filtered and capped.

Further optional tuning:

- after the next real trading wave, rerun `ai_prompt_log_analyzer.py --hours 2`;
- if prompt p90 remains above 5k while decisions do not improve, test `AI_TRADER_MAX_SYMBOLS=10`;
- if fast traders miss movers, increase movement slots or lower liquidity slots in `trading_feature_contract.py`;
- if KB still returns generic content, temporarily disable trader KB or replace it with a deterministic SQL-derived lesson/risk table.
