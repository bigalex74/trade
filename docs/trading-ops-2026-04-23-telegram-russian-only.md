# Trading Ops 2026-04-23: Telegram Russian-Only Rule

## Rule

All Telegram messages sent by the trading system must be strictly in Russian.

This includes:

- daily reports;
- hourly reports;
- watchdog alerts;
- trader notifications;
- postmarket status messages;
- degraded/fallback reports;
- Telegram captions and text chunks.

Technical console logs may remain English when they are not sent to Telegram.

## Changes Applied

Updated Telegram-facing text in:

- `/home/user/ai_daily_report.py`
- `/home/user/ai_evolution.py`
- `/home/user/ai_genetic_incubator.py`
- `/home/user/ai_watchdog_analyzer.py`
- `/home/user/ai_watchdog.py`
- `/home/user/ai_paper_trader.py`

Daily report changes:

- report title/caption translated to Russian;
- AI quality degradation warning translated to Russian;
- deterministic fallback lesson text translated to Russian;
- staff recommendations label translated to Russian;
- fallback staff recommendation translated to Russian;
- chart title translated to Russian.

Postmarket status notifications:

- Evolution completed notification translated;
- Incubator completed notification translated;
- SRE audit completed notification translated.

Watchdog:

- queue alert heading translated.

Trader model-switch fallback:

- default trader label changed from `AI Trader` to `AI трейдер`.

## Verification

Passed:

```bash
/home/user/trading_venv/bin/python -m py_compile \
  /home/user/ai_daily_report.py \
  /home/user/ai_evolution.py \
  /home/user/ai_genetic_incubator.py \
  /home/user/ai_watchdog_analyzer.py \
  /home/user/ai_watchdog.py \
  /home/user/ai_paper_trader.py

rg "<b>[A-Z][A-Z _()]+</b>|FINAL|COMPLETE|COMPLETED|REPORT|DEGRADED|Total Traders|STAFF RECOMMENDATIONS|Telegram report|uploaded to|Technical health|WATCHDOG ALERT|AI Trader" \
  /home/user/ai_daily_report.py \
  /home/user/ai_evolution.py \
  /home/user/ai_genetic_incubator.py \
  /home/user/ai_watchdog_analyzer.py \
  /home/user/ai_watchdog.py \
  /home/user/ai_paper_trader.py

AI_TEST_MODE=1 AI_DAILY_REPORT_SKIP_AI=1 \
  /home/user/trading_venv/bin/python /home/user/ai_daily_report.py
```

The grep check only found environment variable names, not Telegram message templates.
