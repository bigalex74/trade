# Trading Ops 2026-04-22: Tuning Phase 3-4

Дата: 2026-04-22 19:10 MSK.

## Контекст

Продолжен план тюнинга после Phase 1-2:

1. Phase 3: risk engine для max exposure, ATR/volatility sizing, cooldown, max actions.
2. Phase 4: matching engine с cash/position checks, commission, slippage, liquidity cap, dry-run.

Криптотрейдеры и MOEX traders остаются остановлены в cron. Изменения подготовлены и протестированы через dry-run/smoke, без запуска живого цикла.

## Что изменено

### `risk_engine.py`

Добавлен отдельный risk layer для MOEX trader path.

Основные проверки:

- `RISK_MAX_SYMBOL_EXPOSURE_PCT`, default `0.25`.
- `RISK_MAX_GROSS_EXPOSURE_PCT`, default `0.80`.
- `RISK_DEFAULT_TRADE_FRACTION`, default `0.10`.
- `RISK_DEFAULT_SELL_FRACTION`, default `0.25`.
- `RISK_ATR_RISK_PCT`, default `0.01`.
- `RISK_MAX_ACTIONS_PER_DECISION`, default `3`.
- `RISK_MAX_ACTIONS_PER_TRADER_DAY`, default `8`.
- `RISK_MAX_PENDING_ORDERS_PER_TRADER`, default `6`.
- `RISK_COOLDOWN_LOSSES`, default `3`.
- `RISK_COOLDOWN_MINUTES`, default `120`.
- `RISK_COMMISSION_BPS`, default `5`.
- `RISK_LIMIT_BUFFER_BPS`, default `8`.
- `RISK_MIN_ORDER_VALUE`, default `100`.

Risk engine учитывает:

- cash и позиции трейдера;
- pending orders как резерв cash/позиции;
- текущие цены;
- ATR, если он есть в feature contract;
- loss streak из `trading.trader_trade_outcomes_v`;
- дневной лимит действий.

Short/cover сейчас намеренно отклоняются с причиной `short_book_not_enabled`, потому что в схеме нет полноценной short book/margin accounting. Это лучше, чем имитировать short через отрицательные позиции без контроля плеча.

### `ai_paper_trader.py`

Live path больше не пишет решения AI напрямую в `trading.journal`.

Новый поток:

1. AI возвращает JSON decisions.
2. `risk_engine.review_actions(...)` принимает/отклоняет действия.
3. В dry-run ничего не пишется.
4. В live accepted actions создают `trading.orders` со статусом `PENDING`.
5. `order_matching_engine.py` уже исполняет заявки и пишет фактические сделки в `trading.journal`.

Это устраняет архитектурный разрыв: раньше `ai_paper_trader.py` писал journal напрямую, а matching engine смотрел `trading.orders`, куда никто из найденных скриптов не писал.

### `order_matching_engine.py`

Matching engine переписан как безопасный исполнитель pending orders.

Добавлено:

- `MATCHING_DRY_RUN=1` / `AI_MATCHING_DRY_RUN=1` с rollback.
- `MATCHING_SLIPPAGE_BPS`, default `5`.
- `MATCHING_COMMISSION_BPS`, default `5`.
- `MATCHING_MAX_VOLUME_PARTICIPATION`, default `0.05`.
- cash check перед buy.
- position check перед sell/stop_loss.
- liquidity cap по `windows.current_day.volume`.
- partial fill через уменьшение `trading.orders.quantity`.
- `REJECTED` status для заявок без cash/position/liquidity.
- журналирование комиссии, slippage и source reason в `trading.journal.reason`.

## Результаты тестов

Запущен новый smoke:

```bash
/home/user/tests/run_tuning_phase3_phase4_smoke.sh
```

Результат: `phase3/phase4 smoke tests passed`.

Проверено:

- Python compile для `risk_engine.py`, `ai_paper_trader.py`, `order_matching_engine.py`, fake Gemini.
- Direct risk review: buy accepted, short rejected.
- `ai_paper_trader.py` dry-run не мутирует `trading.orders`.
- `ai_paper_trader.py` short action отклоняется risk layer.
- `order_matching_engine.py` dry-run исполняет тестовую заявку внутри транзакции и откатывает изменения.
- Повторно прогнан Phase 1-2 smoke, результат: `phase1/phase2 smoke tests passed`.

Наблюдение по реальным данным:

- У `Chaos_Bill` production risk заблокировал BUY SBER/AFLT при default gross cap, потому что gross exposure уже около 79.4% equity при лимите 80%.
- Acceptance smoke для buy был проверен только с тестовым `RISK_MAX_GROSS_EXPOSURE_PCT=1.0`; рабочий default не менялся.

## Проверки качества

Успешно:

```bash
/home/user/trading_venv/bin/python -m py_compile \
  /home/user/risk_engine.py \
  /home/user/ai_paper_trader.py \
  /home/user/order_matching_engine.py \
  /home/user/tests/fake_gemini_cli.py

bash -n /home/user/tests/run_tuning_phase3_phase4_smoke.sh
```

`git diff --check` по измененным в этом блоке файлам чистый.

Общий `git diff --check` по `/home/user` сейчас показывает trailing whitespace в уже измененных ранее, неродственных файлах:

- `crypto_pipeline.py`
- `telegram-apps/main.py`
- `telegram-apps/static/trade/index.html`

Эти файлы в Phase 3-4 не правились.

## Важные решения

- Direct journal write отключен для новых live AI trader decisions. Journal теперь должен отражать только исполненные сделки.
- Short/cover заблокированы до отдельного margin/short accounting.
- Risk layer не меняет AI-решения семантически, а только ограничивает размер/исполнение через cash/exposure/liquidity/cooldown.
- Matching engine получил dry-run, чтобы тестировать исполнение без порчи портфелей.

## Следующий блок

Остались пункты плана:

1. Market regime layer: отдельная таблица/refresh job `analytics.market_regime`.
2. Meta_Oracle weighted consensus: веса агентов по rolling risk-adjusted score.
3. Evolution candidate pipeline: кандидаты, validation, backtest, promotion без прямой nightly-mutation DNA.
4. Sentiment как risk input: weights, dedup, freshness, confidence.
5. Backtester-gated release: каждое изменение стратегии через backtest/holdout.
6. Временное AI I/O debug logging из плана `trading-ops-2026-04-22-ai-logging-testing-plan.md`.
