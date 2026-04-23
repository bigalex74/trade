# Trading Ops: Trader Pause 2026-04-22

## Context

User requested to stop traders temporarily on 2026-04-22.

## Actions

1. Disabled new trader starts in crontab:
   - commented `run_ai_job_dispatcher.sh`;
   - commented `run_matching_engine_once.sh`.

2. Stopped active MOEX trader jobs:
   - `Passive_Palych`;
   - `PriceAction_Nikita`.

3. Terminated their worker/paper-trader/Gemini process groups.

4. Updated `trading.ai_jobs`:
   - marked queued/running `trader` and `hourly_report` jobs for `moex` and `crypto` as `skipped`;
   - set error text to `paused by user on 2026-04-22`.

## Verification

At `2026-04-22 13:39:25 MSK`:

- no active `ai_job_worker.py` processes;
- no active `ai_paper_trader.py` or `ai_crypto_trader.py` processes;
- no trader Gemini prompts matching `Act as ...`;
- no queued/running rows remain in `trading.ai_jobs`;
- crontab keeps the AI job queue block disabled with `DISABLED 2026-04-22 trader pause` comments.

## Resume Notes

To resume traders, uncomment these crontab lines:

- `* * * * * /home/user/run_ai_job_dispatcher.sh >> /home/user/logs/ai_job_dispatcher.log 2>&1`
- `* 10-23 * * 1-5 /home/user/run_matching_engine_once.sh >> /home/user/logs/traders/matching_engine.log 2>&1`

Crypto remains separately paused by earlier `DISABLED 2026-04-22 crypto paused` cron comments.
