# Market Research Trader Context Handoff

Дата: 2026-04-19

## Цель

Перевести сбор свечей и торговый контекст в одну БД `market_research`, без мостов и without dependency на `trading_core`, чтобы AI-трейдеры брали уже готовый multi-timeframe context из той же БД, где живут `trading.*`.

## Что сделано

### 1. Новый единый pipeline

Добавлен файл:

- `/home/user/market_research_market_pipeline.py`

Он делает две вещи:

1. `collect --interval 1m|1h|1d`
   - собирает свечи напрямую с MOEX;
   - пишет их в `market_research.raw.candle`;
   - использует активный universe из `ref.instrument`;
   - работает без отдельной промежуточной БД.

2. `refresh-context --mode daily|intraday`
   - строит агрегированные окна в `analytics.trader_market_windows`;
   - публикует готовый JSON-контекст через `analytics.trader_market_context_v`.

### 2. Контекст для трейдеров

Созданы:

- `analytics.trader_market_windows`
- `analytics.trader_market_windows_v`
- `analytics.trader_market_context_v`

`analytics.trader_market_context_v` дает одну строку на `secid` и готовый JSON `windows` со срезами:

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

Дополнительно view отдает:

- `current_price`
- `five_min_change_pct`
- `hour_change_pct`
- `day_change_pct`
- `updated_at`

### 3. AI-контур переключен на новый context

Обновлены:

- `/home/user/market_research_context.py`
- `/home/user/ai_paper_trader.py`
- `/home/user/ai_hourly_report.py`
- `/home/user/ai_daily_report.py`
- `/home/user/get_market_snapshot.py`

Теперь:

- трейдер больше не читает `analytics.latest_snapshot`;
- контекст по тикеру не затирается случайным таймфреймом;
- в prompt у AI идут уже готовые multi-timeframe окна;
- отчеты и snapshot берут корректную `current_price` из `analytics.trader_market_context_v`.

### 4. Cron переведен на новую схему

Установлен новый блок:

```cron
## BEGIN MARKET_RESEARCH TRADER PIPELINE
2-57/5 10-23 * * 1-5 /home/user/run_market_research_collect_1m.sh >> /home/user/logs/market_research_collect_1m.log 2>&1
4-59/5 10-23 * * 1-5 /home/user/run_market_research_refresh_intraday.sh >> /home/user/logs/market_research_refresh_intraday.log 2>&1
7 10-23 * * 1-5 /home/user/run_market_research_collect_1h.sh >> /home/user/logs/market_research_collect_1h.log 2>&1
20 8 * * 1-5 /home/user/run_market_research_collect_1d.sh >> /home/user/logs/market_research_collect_1d.log 2>&1
25 8 * * 1-5 /home/user/run_market_research_refresh_daily.sh >> /home/user/logs/market_research_refresh_daily.log 2>&1
## END MARKET_RESEARCH TRADER PIPELINE
```

Shell wrappers:

- `/home/user/run_market_research_collect_1m.sh`
- `/home/user/run_market_research_collect_1h.sh`
- `/home/user/run_market_research_collect_1d.sh`
- `/home/user/run_market_research_refresh_daily.sh`
- `/home/user/run_market_research_refresh_intraday.sh`

Все wrappers используют `flock`, чтобы соседние прогоны не дрались между собой.

## Архитектура

```text
MOEX ISS
  -> market_research.raw.candle
  -> market_research.analytics.trader_market_windows
  -> market_research.analytics.trader_market_context_v
  -> ai_paper_trader.py / ai_hourly_report.py / ai_daily_report.py / get_market_snapshot.py
  -> trading.portfolio / trading.position / trading.journal
```

Ключевой принцип: и market data, и trader state живут в одной БД `market_research`.

## Ревью и найденные проблемы

### Найденный дефект 1

Старый AI-контур читал:

- `SELECT secid, latest_close, change_pct FROM analytics.latest_snapshot`

Но `analytics.latest_snapshot` содержит одну строку на `secid + interval_name`, а не одну строку на `secid`.

После этого код собирал словарь вида:

```python
{secid: {"price": ..., "change": ...}}
```

Из-за этого строки разных таймфреймов затирали друг друга, и трейдер мог видеть цену/изменение из произвольного интервала.

Статус:

- исправлено;
- заменено на `analytics.trader_market_context_v`.

### Найденный дефект 2

Сбор свечей и потребление контекста были разведены между двумя контурами:

- `trading_core`
- `market_research`

Это создавало лишнюю связность и риск рассинхрона.

Статус:

- исправлено;
- теперь используется одна БД `market_research`.

### Найденный дефект 3

Для трейдеров не было отдельного стабильного контракта данных под multi-timeframe context.

Статус:

- исправлено;
- контракт вынесен в `analytics.trader_market_context_v`.

## Фактическая проверка

После внедрения pipeline был прогнан вручную:

- `collect 1d`
- `collect 1h`
- `collect 1m`
- `refresh-context --mode daily`
- `refresh-context --mode intraday`

Результат:

- `1d`: добавлены новые строки, в том числе для `NGH6`
- `1h`: добавлено `315` строк
- `1m`: добавлено `60756` строк
- `analytics.trader_market_context_v`: `27` тикеров в контексте, `24` с price

Проверка контекста показала, что для `SBER`, `GAZP`, `USD000UTSTOM` и других инструментов уже доступны все окна `5m/hour/day/week/month/year`.

## Остаточные риски

1. Для части инструментов MOEX сейчас не вернул ряд:
   - `BRENT`
   - `TCSG`
   - `YNDX`

2. Для `NGH6` есть day/week/month/year, но нет полноценного intraday window set.

3. В старой схеме могут остаться внешние consumers, которые все еще читают `analytics.latest_snapshot`. Для AI-трейдеров это уже исправлено, но остальные потребители нужно проверять отдельно.

## План следующих улучшений

1. Добавить health-check script по `raw.candle` и `analytics.trader_market_context_v`, чтобы cron не молчал при деградации данных.
2. Сохранить в БД метрики freshness по каждому `secid + interval`, чтобы проще ловить отстающие инструменты.
3. Отдельно решить universe для тикеров без данных от MOEX:
   - либо деактивировать в `ref.instrument`,
   - либо дать им отдельный backfill/альтернативный источник.
4. Если AI-трейдеры начнут реально исполнять сделки, вынести формирование prompt-context в отдельный service/module с versioned schema.

## Список ключевых файлов

- `/home/user/market_research_market_pipeline.py`
- `/home/user/market_research_context.py`
- `/home/user/ai_paper_trader.py`
- `/home/user/ai_hourly_report.py`
- `/home/user/ai_daily_report.py`
- `/home/user/get_market_snapshot.py`
- `/home/user/run_market_research_collect_1m.sh`
- `/home/user/run_market_research_collect_1h.sh`
- `/home/user/run_market_research_collect_1d.sh`
- `/home/user/run_market_research_refresh_daily.sh`
- `/home/user/run_market_research_refresh_intraday.sh`
