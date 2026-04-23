# Trading Ops 2026-04-22: MOEX Traders Enabled

Дата: 2026-04-22 19:25 MSK.

## Что включено

Биржевые трейдеры MOEX включены обратно через cron.

Активный блок:

```cron
## BEGIN AI_JOB_QUEUE
5-55/5 10-23 * * 1-5 /home/user/run_market_regime_refresh.sh >> /home/user/logs/market_regime.log 2>&1
* * * * * /home/user/run_ai_job_dispatcher.sh >> /home/user/logs/ai_job_dispatcher.log 2>&1
* 10-23 * * 1-5 /home/user/run_matching_engine_once.sh >> /home/user/logs/traders/matching_engine.log 2>&1
17 3 * * * /home/user/run_logrotate_trading.sh >> /home/user/logs/logrotate_trading.log 2>&1
## END AI_JOB_QUEUE
```

Крипта осталась выключена:

- `crypto_pipeline.py` disabled.
- `ai_crypto_daily_report.py` disabled.
- `AI_ENABLE_CRYPTO_AI=0` в `run_ai_job_dispatcher.sh`.

## Логирование

В `run_ai_trader_once.sh` включено временное debug I/O логирование:

```bash
AI_DEBUG_IO_LOG=1
AI_DEBUG_IO_MAX_CHARS=60000
```

Цель: собрать реальные prompt/response для анализа качества и объема входов AI.

Данные пишутся в:

- `trading.ai_call_log`: метаданные вызовов, статусы, размеры, ошибки.
- `trading.ai_io_debug_log`: prompt/response payload, только пока включен `AI_DEBUG_IO_LOG=1`.

## Первый ручной контрольный запуск

Запущено:

```bash
/home/user/run_ai_trader_once.sh Chaos_Bill
```

Результат:

- prompt size: `3129` chars.
- `gemini-3-flash-preview`: `exhausted`, 429/capacity.
- `gemini-2.5-flash`: `exhausted`, 429/capacity.
- fallback budget stopped at 2 attempts.
- AI decision not produced.
- `trading.orders`: no new orders.
- `trading.ai_io_debug_log`: 2 rows created for `Chaos_Bill`.

## Market regime

`run_market_regime_refresh.sh` executed successfully.

Latest regime:

- `mixed`
- `YELLOW`
- `risk_multiplier=0.8`
- `breadth_pct=66.667`
- `sample_size=21`

## Matching engine

Matching engine cron is active and running once per minute during MOEX hours.

Initial status:

- pending orders: `0`
- fills: `0`
- rejects: `0`

## Notes

Event-gate at 19:20 MSK was inactive:

- max 5m move around `0.12%`
- max 1h move around `0.27%`

With current dispatcher settings, if no event wave is triggered, the next full wave starts at the next minute divisible by 30. At this point the next full wave should be `19:30 MSK`.

## 19:30 MSK cron wave confirmation

Full wave confirmed:

- `run_ai_job_dispatcher.sh` queued 11 MOEX trader jobs at `19:30 MSK`.
- Worker pool started jobs in staggered mode.
- At the first control slice there were `7 queued` and `2 running` MOEX jobs.
- `Chaos_Bill` and `Contrarian_Ricardo` already failed with Gemini 429/capacity.
- `trading.ai_io_debug_log` had 6 trader debug rows for the last 15 minutes.
- Pending orders remained `0`, because no AI decision was produced.

Observed prompt sizes:

- `Chaos_Bill`: about `3116-3129` chars.
- `Contrarian_Ricardo`: about `6359` chars.

Current blocker is not local script execution; it is Gemini CLI quota/capacity returning 429.

## Fallback expanded

По запросу пользователя fallback для MOEX trader calls расширен до 6 моделей.

Порядок:

1. `gemini-3.1-pro-preview`
2. `gemini-3-flash-preview`
3. `gemini-3.1-flash-lite-preview`
4. `gemini-2.5-pro`
5. `gemini-2.5-flash`
6. `gemini-2.5-flash-lite`

Изменено:

- `ai_paper_trader.py`: default `trader_models()`.
- `run_ai_trader_once.sh`: `AI_TRADER_MODELS` default и `AI_MAX_FALLBACKS_TRADER=5`, то есть до 6 total attempts.
- `ai_model_rank.json`: global priority приведен к тому же порядку.
- `ollama/llama3.2` отключен для MOEX trader fallback, потому что пользователь задал конкретный Gemini-only список, а локальный `ollama` binary отсутствует и засорял логи `FileNotFoundError`.

Проверка:

- `python -m py_compile ai_paper_trader.py gemini_cli_runner.py`
- `bash -n run_ai_trader_once.sh`
- `python -m json.tool ai_model_rank.json`
- fake Gemini dry-run `Chaos_Bill` подтвердил, что первым используется `gemini-3.1-pro-preview`.

Важно: общий `GEMINI_TIMEOUT_SECONDS` остался `120` секунд. Если модели отвечают 429 быстро, цепочка пройдет глубже; если зависают, общий timeout все равно ограничит цикл.

## Follow-up

Monitor:

```sql
SELECT created_at, trader_name, model_id, status, prompt_chars, response_chars, error_class, left(error, 160)
FROM trading.ai_call_log
WHERE created_at > clock_timestamp() - interval '2 hours'
ORDER BY created_at DESC;

SELECT created_at, trader_name, model_id, status, prompt_chars, response_chars, truncated
FROM trading.ai_io_debug_log
WHERE created_at > clock_timestamp() - interval '2 hours'
ORDER BY created_at DESC;

SELECT id, trader_name, secid, order_type, quantity, target_price, status, created_at
FROM trading.orders
ORDER BY created_at DESC
LIMIT 20;
```

Disable `AI_DEBUG_IO_LOG=1` after the tuning sample is collected to avoid DB growth.
