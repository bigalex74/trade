# Market Research Maintenance Handoff

Дата: 2026-04-19

## Что добавлено

### 1. Maintenance script

Добавлен:

- `/home/user/market_research_maintenance.py`

Поддерживает две команды:

1. `cleanup-intraday-history`
   - удаляет из `market_research.raw.candle` все свечи `1m` и `1h`, которые старше начала текущего дня по Москве;
   - дневные и недельные интервалы не трогает;
   - нужен, чтобы не копить старый intraday-хвост, который больше не участвует в текущем дне.

2. `health-check`
   - проверяет свежесть `raw.candle` и `analytics.trader_market_context_v`;
   - возвращает код `0`, если все ок, и `1`, если данные stale или контекст неполный;
   - подходит для cron и внешнего мониторинга.

### 2. Shell wrappers

Добавлены:

- `/home/user/run_market_research_cleanup_intraday.sh`
- `/home/user/run_market_research_healthcheck.sh`

Оба используют `flock`, чтобы задания не запускались параллельно.

## Cron

Текущий cron-блок:

```cron
## BEGIN MARKET_RESEARCH TRADER PIPELINE
5 8 * * 1-5 /home/user/run_market_research_cleanup_intraday.sh >> /home/user/logs/market_research_cleanup_intraday.log 2>&1
20 8 * * 1-5 /home/user/run_market_research_collect_1d.sh >> /home/user/logs/market_research_collect_1d.log 2>&1
25 8 * * 1-5 /home/user/run_market_research_refresh_daily.sh >> /home/user/logs/market_research_refresh_daily.log 2>&1
35 8 * * 1-5 /home/user/run_market_research_healthcheck.sh >> /home/user/logs/market_research_healthcheck.log 2>&1
2-57/5 10-23 * * 1-5 /home/user/run_market_research_collect_1m.sh >> /home/user/logs/market_research_collect_1m.log 2>&1
4-59/5 10-23 * * 1-5 /home/user/run_market_research_refresh_intraday.sh >> /home/user/logs/market_research_refresh_intraday.log 2>&1
7 10-23 * * 1-5 /home/user/run_market_research_collect_1h.sh >> /home/user/logs/market_research_collect_1h.log 2>&1
11,26,41,56 10-23 * * 1-5 /home/user/run_market_research_healthcheck.sh >> /home/user/logs/market_research_healthcheck.log 2>&1
## END MARKET_RESEARCH TRADER PIPELINE
```

## Логика cleanup

Cleanup удаляет:

- `raw.candle.interval_name = '1m'`
- `raw.candle.interval_name = '1h'`

если `candle_time < начало текущего дня Europe/Moscow`.

Это означает:

- утром нового дня intraday-ряд стартует "с нуля";
- для `5m/hour/current_day` дальше используются только свежие данные текущего дня;
- `previous_day/week/month/year` продолжают строиться из `1d`, поэтому контекст трейдеров не ломается.

## Логика health-check

Проверяется:

1. количество активных инструментов в `ref.instrument`;
2. количество строк и priced rows в `analytics.trader_market_context_v`;
3. `max(updated_at)` у trader context;
4. `max(candle_time)` по `1m`, `1h`, `1d`, `1w`.

Условия:

- `context_rows` должно покрывать весь active universe;
- `priced_rows` должен быть почти полным;
- `1d` не должен быть старше 7 дней;
- в торговую сессию `1m` не должен быть старше 25 минут;
- в торговую сессию `1h` не должен быть старше 3 часов;
- `trader_market_context_v` не должен быть stale.

## Фактическая проверка

### Health-check

Ручной запуск `health-check --json` вернул `status = ok`.

На момент проверки:

- `active_instruments = 27`
- `context_rows = 27`
- `priced_rows = 24`
- `latest_context_update = 2026-04-19T06:44:18.388464+00:00`

### Cleanup dry-run

Ручной dry-run показал:

- `1m` к удалению: `75293`
- `1h` к удалению: `5812`

Это ожидаемо, потому что проверка делалась вне нового торгового дня, и весь накопленный intraday-хвост относится к предыдущим дням.

Важно:

- destructive cleanup вручную не запускался;
- он поставлен в cron на будни `08:05`, чтобы работать в правильном месте жизненного цикла дня.

## Риски

1. Если появится внешний consumer, которому нужен intraday-архив за прошлые дни, ему уже нельзя будет читать `raw.candle` для `1m/1h`; потребуется отдельное архивное хранилище.
2. `health-check` сейчас логирует ошибку и выходит с non-zero code, но сам по себе не шлет уведомления в Telegram.

## Следующий логичный шаг

1. Добавить алертинг на `market_research_healthcheck.log` или прямую отправку в Telegram при non-zero статусе.
2. При желании вынести intraday cleanup retention из бинарного режима "только текущий день" в параметр, например хранить последние `N` московских дней.
