# 2026-04-23 Git Sync And Runner Fixes

## Context

Local trading-system fixes were rebased on top of `origin/master` after pulling 13 remote commits.
Conflicts were resolved in trader scripts, job queue wrappers, watchdog, matching engine and Qdrant compose.

## Fixes During Sync

- `ai_paper_trader.py` and `ai_crypto_trader.py` no longer call `gemini` directly with 900s timeout.
- MOEX trader AI calls now go through `gemini_cli_runner`, so `GEMINI_BIN`, clean workdir, 120s timeout, flock, cost guard, model cooldown and debug I/O logging apply.
- `ai_paper_trader.py` now uses compact `MARKET FEATURES` from `trading_feature_contract.py` instead of full market windows in the AI prompt.
- `ai_paper_trader.py` now runs decisions through `risk_engine.review_actions` and writes pending orders instead of direct portfolio/journal mutations.
- `AI_TRADER_DRY_RUN=1` prevents trader DB mutations and logs the risk review result.
- `order_matching_engine.py` supports `MATCHING_DRY_RUN=1` and rolls back would-be fills.
- `tests/fake_gemini_cli.py` now prioritizes trader JSON prompts before generic sentiment prompts.
- Removed a duplicated broken tail in `ai_crypto_trader.py` that caused a syntax error.

## Verification

- Python compile passed for key trading, runner, risk and reporting scripts.
- Bash syntax check passed for key wrapper scripts.
- `tests/run_tuning_phase3_phase4_smoke.sh` passed, including nested phase1/phase2 checks.
- `tests/run_tuning_phase5_phase9_smoke.sh` passed.

