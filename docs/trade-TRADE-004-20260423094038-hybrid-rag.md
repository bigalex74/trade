# Гибридная RAG-память трейдеров

Дата: 2026-04-23

Ветка изменения: `TRADE-004`

Версия проекта после изменения: `0.2.0`

## Цель

Сделать из идеи гибридного RAG рабочую подсистему, которая помогает трейдерам получать короткий релевантный контекст без раздувания prompt и без дополнительных расходов на внешние embeddings.

## Что реализовано

Добавлен модуль:

```text
hybrid_rag.py
```

Он содержит:

- клиент Qdrant;
- embeddings-клиент;
- индексацию закрытых сделок;
- индексацию новостей;
- retrieval для трейдерского prompt;
- форматирование компактного блока `HYBRID RAG CONTEXT`.

Переписан CLI:

```text
ai_memory_indexer.py
```

Теперь это безопасный индексатор с режимами:

```bash
python ai_memory_indexer.py --mode all
python ai_memory_indexer.py --mode setups
python ai_memory_indexer.py --mode news
```

Добавлен wrapper:

```text
run_ai_memory_indexer.sh
```

Он использует flock и общие env-настройки проекта.

В cron добавлен регулярный refresh Qdrant в торговые часы:

```text
3,18,33,48 10-23 * * 1-5 /home/user/trade/run_ai_memory_indexer.sh --mode all --lookback-days 60 --news-lookback-hours 168 --limit 500 --json >> /home/user/logs/ai_memory_indexer.log 2>&1
```

## Коллекции Qdrant

Сделки:

```text
trade_setups_memory_v1
```

Новости:

```text
market_news_memory_v1
```

Qdrant URL по умолчанию:

```text
http://localhost:6333
```

## Embeddings

По умолчанию используется локальная Ollama-модель:

```text
nomic-embed-text
```

Это не расходует Gemini-токены.

Для тестов доступен deterministic hash-provider:

```bash
AI_RAG_EMBEDDING_PROVIDER=hash
```

## Память сделок

Индексируются закрытые сделки из PostgreSQL:

```text
market_research.trading.journal
```

Индексируются и прибыльные, и убыточные исходы. Это важно, чтобы не создать survivorship bias.

Для каждой сделки сохраняется:

- трейдер;
- тикер;
- путь сделки `BUY->SELL` или `SHORT->COVER`;
- PnL в процентах;
- причина входа;
- причина выхода;
- краткий snapshot индикаторов;
- время входа и выхода;
- модель;
- стабильный `source_key`;
- `source_hash` для идемпотентной переиндексации с учетом provider/model embeddings.

## Память новостей

Новости берутся из:

```text
market_research.raw.news_item
market_research.raw.news_instrument_match
market_research.ref.instrument
```

В Qdrant сохраняются:

- источник;
- дата публикации;
- заголовок;
- краткое содержание;
- ссылка;
- связанные тикеры.

При retrieval применяется TTL:

```text
AI_RAG_NEWS_MAX_AGE_HOURS=168
```

## Интеграция в трейдера

`ai_paper_trader.py` теперь добавляет в prompt короткий блок:

```text
HYBRID RAG CONTEXT
```

В блок попадает:

- до `AI_RAG_SETUPS_LIMIT` похожих исторических исходов;
- до `AI_RAG_NEWS_LIMIT` свежих новостных записей;
- предупреждение, что это только дополнительный risk-context.

Если Qdrant или embeddings недоступны, трейдер продолжает работу без RAG-контекста.

## Настройки

Основные переменные:

```text
AI_RAG_ENABLED=1
AI_RAG_QDRANT_URL=http://localhost:6333
AI_RAG_EMBEDDING_PROVIDER=ollama
AI_RAG_EMBEDDING_MODEL=nomic-embed-text
AI_RAG_SETUPS_COLLECTION=trade_setups_memory_v1
AI_RAG_NEWS_COLLECTION=market_news_memory_v1
AI_RAG_SETUPS_LIMIT=3
AI_RAG_NEWS_LIMIT=3
AI_RAG_MAX_CHARS=700
AI_RAG_NEWS_MAX_AGE_HOURS=168
```

## Guardrails

- Qdrant не принимает торговых решений.
- RAG-блок не заменяет `MARKET FEATURES`.
- Risk engine остается обязательным фильтром действий.
- Matching engine остается единственным исполнителем pending orders.
- Повторная индексация не создает дубликаты благодаря стабильному UUID и `source_hash`, но корректно обновляет векторы при смене embeddings-provider.
- Индексатор теперь чистит устаревшие точки Qdrant, которые вышли из текущего окна lookback.
- Индексатор запускается по cron с `flock`, поэтому параллельные refresh-процессы не накладываются друг на друга.
- Размер RAG-блока ограничен, чтобы не вернуть проблему переполненных prompt.
- Для штатного запуска `run_ai_trader_once.sh` по умолчанию ограничивает выборку рынка `AI_TRADER_MAX_SYMBOLS=8`, чтобы оставить место под RAG-контекст без превышения AI prompt budget.
- Если итоговый prompt все равно превышает лимит, `ai_paper_trader.py` автоматически ужимает или отключает RAG-блок.
- Новости имеют TTL.
- При ошибке RAG не блокирует работу трейдера.

## Тесты

Добавлен smoke-тест:

```bash
tests/run_hybrid_rag_smoke.sh
```

Он проверяет:

- компиляцию `hybrid_rag.py`, `ai_memory_indexer.py`, `ai_paper_trader.py`;
- индексацию synthetic закрытой сделки;
- индексацию synthetic новости;
- retrieval блока для трейдера;
- идемпотентность повторной индексации;
- очистку smoke-коллекций Qdrant после теста.

## Следующие улучшения

1. Добавить метрики влияния RAG на решения: с памятью и без памяти.
2. Добавить holdout-gate перед увеличением лимитов RAG-контекста.
3. Добавить отдельный analyzer, который покажет, какие retrieved items реально попали в prompt и повлияли на решение.
4. После накопления данных сделать отдельные коллекции по режимам рынка, если общая коллекция начнет давать шум.
