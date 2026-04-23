# Trading Ops 2026-04-22: Tuning Phase 5-9

Дата: 2026-04-22 19:20 MSK.

## Контекст

Продолжен исходный план тюнинга после Phase 1-4:

5. Market regime layer.
6. Meta_Oracle weighted consensus.
7. Evolution candidate pipeline.
8. Sentiment как risk input.
9. Backtester-gated release.
10. Временное AI I/O debug logging для тюнинга входов/ответов.

## Что изменено

### Market regime

Добавлен `market_regime.py`.

Создает и обновляет таблицу:

- `analytics.market_regime`

Метрики:

- `regime`
- `risk_level`
- `risk_multiplier`
- `breadth_pct`
- `avg_day_change_pct`
- `avg_hour_change_pct`
- `avg_intraday_range_pct`
- `sample_size`
- `details`

Добавлен запуск:

- `run_market_regime_refresh.sh`

Текущий refresh на момент теста:

- regime: `mixed`
- risk_level: `YELLOW`
- risk_multiplier: `0.8`
- breadth_pct: `61.905`
- avg_day_change_pct: `0.438`
- avg_hour_change_pct: `0.051`
- avg_intraday_range_pct: `1.725`
- sample_size: `21`

`ai_paper_trader.py` теперь добавляет compact regime в prompt и умножает risk multiplier трейдера на `analytics.market_regime.risk_multiplier`.

### Meta_Oracle weighted consensus

Добавлен `trader_consensus.py`.

Логика:

- берет веса агентов из `trading.trader_performance_v`;
- вес зависит от `tuning_score`;
- вес штрафуется за `ai_failure_rate_pct`;
- читает последние BUY/SELL из `trading.journal`;
- строит compact consensus: `net_score`, `buy_weight`, `sell_weight`, `confidence`, `traders`, `last_at`.

`ai_paper_trader.py` добавляет `META_CONSENSUS` только для `Meta_Oracle`. Сейчас consensus может быть пустым, если в последние 24 часа нет сделок, это нормальное состояние при остановленных трейдерах.

### Evolution candidate pipeline

Добавлен `strategy_candidate_pipeline.py`.

Создает таблицу:

- `trading.strategy_candidates`

Поля:

- `source`
- `trader_name`
- `title`
- `candidate_text`
- `status`
- `validation_status`
- `backtest_run_id`
- `promoted_at`
- `metadata`

Обновлены:

- `ai_evolution.py`
- `ai_genetic_incubator.py`

Теперь качественный AI-отчет не становится прямой мутацией DNA. Он сохраняется как candidate со статусом `PROPOSED` и `auto_promote=False`, затем может пройти release gate/backtest.

### Sentiment как risk input

`ai_paper_trader.py` теперь читает свежий sentiment из:

- `analytics.market_sentiment`

Свежесть: последние 24 часа.

В prompt попадает только compact sentiment для выбранных feature symbols:

- `sent_score`
- `sent_age_h`

В `risk_engine.py` sentiment применяется как защитный risk input:

- `sent_score <= -0.6`: BUY отклоняется с `negative_sentiment_risk`;
- `-0.6 < sent_score <= -0.3`: buy budget режется на 50%;
- stale sentiment старше 24 часов не используется.

Текущая таблица sentiment пока не хранит source weights/dedup/confidence; это следующий точечный апгрейд схемы sentiment, если понадобится глубокая новостная агрегация.

### Backtester-gated release

Добавлен `strategy_release_gate.py`.

Логика:

- candidate не может быть promoted без backtest run;
- backtest run должен иметь `status='succeeded'`;
- проверяется `return_pct >= min_return_pct`;
- проверяется `max_drawdown_pct >= max_drawdown_pct` threshold;
- при pass статус candidate может стать `BACKTEST_PASSED`;
- прямой автоматической мутации DNA нет.

Smoke подтвердил expected block:

- reason: `backtest_required`.

### AI I/O debug logging

Обновлен `ai_cost_guard.py`.

Добавлена таблица:

- `trading.ai_io_debug_log`

Логирование выключено по умолчанию.

Включение:

```bash
AI_DEBUG_IO_LOG=1
```

Ограничение размера:

```bash
AI_DEBUG_IO_MAX_CHARS=60000
```

Пишутся:

- full/trimmed prompt text;
- full/trimmed response text;
- script/call/category/trader/model/status;
- original prompt/response chars;
- флаг `truncated`.

Это временный инструмент для тюнинга входных данных. В обычном режиме он не пишет payload и не раздувает базу.

## Тесты

Запущено:

```bash
/home/user/tests/run_tuning_phase5_phase9_smoke.sh
/home/user/tests/run_tuning_phase3_phase4_smoke.sh
```

Результаты:

- `phase5/phase9 smoke tests passed`
- `phase3/phase4 smoke tests passed`
- Phase3/4 smoke внутри повторно прогнал Phase1/2 smoke: `phase1/phase2 smoke tests passed`

Проверено:

- compile новых и измененных Python scripts;
- market regime refresh создает свежую строку;
- latest regime читается compact helper;
- weighted consensus не падает при пустом журнале последних 24 часов;
- sentiment risk блокирует свежий сильно негативный BUY;
- strategy release gate блокирует candidate без backtest;
- AI debug I/O пишет prompt/response только при `AI_DEBUG_IO_LOG=1`;
- trader dry-run работает с regime/sentiment/consensus hooks;
- matching dry-run все еще делает rollback.

## Важные ограничения

- Short/cover остаются заблокированы до отдельной short book/margin модели.
- Market regime пока агрегирует только текущий stock universe из `analytics.trader_market_context_v`.
- Sentiment risk использует текущую простую `analytics.market_sentiment`; source weighting/dedup/confidence еще не хранится в схеме.
- Release gate не запускает backtest сам, а валидирует уже сохраненный `trading.ai_backtest_runs`.

## Текущее состояние

Трейдеры остаются остановлены в cron. Все изменения проверены в dry-run/smoke. Перед возвращением live-режима нужно отдельно решить:

1. Как часто запускать `run_market_regime_refresh.sh`.
2. Какие thresholds поставить для `strategy_release_gate.py`.
3. Включать ли `AI_DEBUG_IO_LOG=1` только на короткое окно тюнинга.
