# Trading Core Market Pipeline Handoff

Date: 2026-04-19

## Что сделано

- Восстановлен и разделен `trading_core` market pipeline вместо одного общего скрипта.
- Добавлен единый pipeline: `/home/user/trading_core_market_pipeline.py`
- Добавлены shell-обертки для `cron`:
  - `/home/user/run_trading_core_collect_1m.sh`
  - `/home/user/run_trading_core_collect_1h.sh`
  - `/home/user/run_trading_core_collect_1d.sh`
  - `/home/user/run_trading_core_refresh_daily.sh`
  - `/home/user/run_trading_core_refresh_intraday.sh`
- В БД `trading_core` добавлена таблица `trader_market_windows`.
- В БД `trading_core` добавлены вьюхи:
  - `trader_market_windows_v` — нормализованное представление по окнам
  - `trader_market_context_v` — один актив = один JSON-контекст со всеми периодами
- Локальный трейдер `/home/user/paper_trader.py` переведен на чтение готового контекста из `trader_market_context_v`.

## Архитектура

### Слой сбора

- `1m` собирается с MOEX напрямую и является базой для `5m` и `hour` контекста.
- `1h` собирается отдельно с MOEX для хранения часового ряда.
- `1D` собирается отдельно с MOEX для day/week/month/year.

### Слой агрегации

- `refresh-context --mode intraday` строит:
  - `current_5m`
  - `previous_5m`
  - `current_hour`
  - `previous_hour`
  - `current_day`
  - `previous_day`
  - `current_week`
  - `previous_week`
  - `current_month`
  - `previous_month`
  - `year`
- `refresh-context --mode daily` обновляет длинные окна без `5m/hour`.

### Вьюхи для трейдеров

- `trader_market_windows_v` — строка на период.
- `trader_market_context_v` — одна строка на тикер, поле `windows` содержит JSON по всем окнам.

Пример формы `windows`:

```json
{
  "current_5m": {
    "close": 324.26,
    "change_pct": 0.01,
    "source_interval": "1m"
  },
  "current_week": {
    "close": 324.26,
    "change_pct": 2.07,
    "source_interval": "mixed"
  }
}
```

## Cron

Активный блок в текущем `crontab`:

```cron
## BEGIN TRADING_CORE MARKET PIPELINE
2-57/5 10-23 * * 1-5 /home/user/run_trading_core_collect_1m.sh >> /home/user/logs/trading_core_collect_1m.log 2>&1
4-59/5 10-23 * * 1-5 /home/user/run_trading_core_refresh_intraday.sh >> /home/user/logs/trading_core_refresh_intraday.log 2>&1
7 10-23 * * 1-5 /home/user/run_trading_core_collect_1h.sh >> /home/user/logs/trading_core_collect_1h.log 2>&1
20 8 * * 1-5 /home/user/run_trading_core_collect_1d.sh >> /home/user/logs/trading_core_collect_1d.log 2>&1
25 8 * * 1-5 /home/user/run_trading_core_refresh_daily.sh >> /home/user/logs/trading_core_refresh_daily.log 2>&1
## END TRADING_CORE MARKET PIPELINE
```

## Текущее состояние данных

На момент handoff:

- `market_data`
  - `1m`: max timestamp `2026-04-18 18:59:00+00`
  - `1h`: max timestamp `2026-04-18 18:00:00+00`
  - `1D`: max timestamp `2026-04-18 00:00:00+00`
- `trader_market_windows`
  - заполнены окна по 30 активам
  - отсутствуют свежие окна у тикеров, по которым MOEX не вернул свежий intraday-ряд

## Важные технические наблюдения

- MOEX endpoint в текущей конфигурации не отдает `5m` напрямую.
- Поэтому `5m` окна строятся локально из `1m`, это штатная и корректная схема.
- Для `1h` были единичные timeout на MOEX, поэтому в pipeline добавлены retry.
- В shell-обертках исправлена обработка `flock`: `skip` и реальная ошибка теперь различаются.

## Что изменено в paper_trader

- Получает готовый контекст через `trader_market_context_v`.
- Берет execution price из наиболее свежего окна:
  - `current_5m`
  - `current_hour`
  - `current_day`
  - fallback на последний `1D close`
- В `trade_history.reason` пишет не только базовый reason, но и агрегированный контекст:
  - `day`
  - `week`
  - `month`
  - `year`

## Следующий логичный шаг

- Перевести AI-трейдеров из контура `market_research` на чтение готового market context из `trading_core`.
- Для этого лучше не тащить их сразу на сырые свечи, а давать им уже собранный JSON-контекст из `trader_market_context_v`.
- Если нужно сохранить разделение БД, можно добавить экспорт/репликацию контекста из `trading_core` в `market_research`.
