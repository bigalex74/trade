# TRADE-010: Увеличение timeout трейдеров

Дата: 2026-04-23

Версия: `0.4.3`

## Задача

Увеличить timeout одной попытки Gemini для MOEX-трейдеров, потому что `35` секунд оказалось мало: часть трейдеров не получала решение, хотя модель могла ответить дольше.

## Изменение

В `run_ai_trader_once.sh`:

```bash
GEMINI_ATTEMPT_TIMEOUT_SECONDS_TRADER=60
```

Раньше было:

```bash
GEMINI_ATTEMPT_TIMEOUT_SECONDS_TRADER=35
```

Общий лимит остался:

```bash
GEMINI_TIMEOUT_SECONDS=120
```

## Ожидаемый эффект

- Старшие Gemini-модели получают больше времени на ответ.
- Должно стать меньше холостых timeout на `gemini-3.1-pro-preview` и `gemini-3-flash-preview`.
- Меньше трейдеров будут простаивать без AI-решения.

## Компромисс

При зависшей модели один трейдер может занимать слот дольше.

С учетом `TRADE-009` сейчас `GEMINI_CONCURRENCY=1`, поэтому это осознанный выбор в пользу качества и стабильности решений, а не максимальной скорости.

## Проверки

Пройдены:

```bash
./tests/run_trader_runtime_config_smoke.sh
./tests/run_ai_fallback_smoke.sh
```

## Следующий контроль

После ближайших торговых волн проверить:

```sql
SELECT trader_name, model_id, status, duration_seconds, created_at
FROM trading.ai_call_log
WHERE category = 'trader'
ORDER BY created_at DESC
LIMIT 80;
```

Критерий: меньше `timeout` на 35 секунд, больше `success` на старших моделях в диапазоне 35-60 секунд.
