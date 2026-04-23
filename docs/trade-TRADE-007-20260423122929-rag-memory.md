# TRADE-007: Расширение наполнения RAG и ALGO KB

Дата: 2026-04-23

Версия: `0.4.0`

## Задача

Проверить и исправить ситуацию, когда в RAG и LightRAG для трейдеров поступает мало данных.

## Что было найдено

- Qdrant RAG работал, но наполнялся только закрытыми сетапами и свежими новостями.
- В ALGO LightRAG было мало свежих trader-facing документов.
- Большинство свежих новостей не имели привязки к тикерам через `raw.news_instrument_match`.
- Live-трейдеры не используют прямой LightRAG-запрос. Основной live-контекст идет через Qdrant RAG.
- Старые переменные `AI_TRADER_KB_*` создавали ложное впечатление, что LightRAG прямо участвует в live decision path.

## Реализовано

1. Добавлена Qdrant-коллекция `market_snapshots_memory_v1`.

В нее индексируются:

- агрегированный снимок рынка;
- режим рынка из `analytics.market_regime`;
- лидеры роста и снижения;
- лидеры движения за час;
- лидеры ликвидности;
- компактные snapshot'ы ключевых тикеров.

2. В live RAG-контекст добавлен блок `RAG_MARKET`.

Порядок блоков теперь:

- `RAG_MARKET`;
- `RAG_NEWS`;
- `RAG_TRADES`.

Это сделано потому, что при лимите `AI_RAG_MAX_CHARS=420` длинная история сделок раньше могла вытеснять свежий рыночный контекст.

3. Улучшен матчинг новостей к тикерам.

Если `raw.news_instrument_match` пустой, индексатор ищет тикеры через:

- `ref.instrument.secid`;
- `ref.instrument.issuer_name`;
- `ref.instrument.news_keywords`.

В payload новости добавляются:

- `secids`;
- `match_sources`;
- `matched_terms`.

4. Добавлен интрадейный ALGO KB digest.

Новый скрипт:

```bash
/home/user/trade/algo_kb_intraday_digest.py
```

Wrapper:

```bash
/home/user/trade/run_algo_kb_intraday_digest.sh
```

Cron:

```cron
15 10-23 * * 1-5 /home/user/trade/run_algo_kb_intraday_digest.sh --top 3 --news-hours 24 --news-limit 3 --focus-limit 8 >> /home/user/logs/algo_kb_intraday_digest.log 2>&1
```

Digest специально компактный: около 1.5-1.8K символов вместо 4.8K в первой версии.

5. Удалены мертвые настройки из runner'а трейдеров:

- `AI_TRADER_KB_CACHE_SECONDS`;
- `AI_TRADER_KB_MAX_CHARS`;
- `AI_TRADER_KB_SYMBOLS`.

Они не использовались `ai_paper_trader.py` и вводили в заблуждение.

## Production-проверка

Индексатор Qdrant после cleanup smoke-данных:

```json
{
  "market": {"seen": 21, "skipped": 21, "indexed": 0, "deleted": 0},
  "news": {"seen": 67, "skipped": 67, "indexed": 0, "deleted": 1, "matched": 10, "keyword_matched": 5},
  "setups": {"seen": 71, "skipped": 71, "indexed": 0, "deleted": 1}
}
```

Текущие Qdrant collections:

- `trade_setups_memory_v1`: 71 точка;
- `market_news_memory_v1`: 67 точек;
- `market_snapshots_memory_v1`: 21 точка.

ALGO KB:

- первый слишком крупный `moex_intraday_digest_2026-04-23_1201.txt` удален;
- compact digest `moex_intraday_digest_2026-04-23_1226.txt` обработан;
- content length нового digest: 1550 символов.

## Тесты

Пройдены проверки:

```bash
/home/user/trading_venv/bin/python -m py_compile hybrid_rag.py ai_memory_indexer.py algo_kb_intraday_digest.py ai_paper_trader.py algo_kb_client.py
./tests/run_hybrid_rag_smoke.sh
./tests/run_algo_kb_intraday_digest_smoke.sh
./tests/run_prompt_compaction_smoke.sh
./run_ai_memory_indexer.sh --mode all --lookback-days 60 --news-lookback-hours 168 --limit 500 --json
```

Дополнительно проверено:

- compact RAG при `AI_RAG_MAX_CHARS=420` содержит `RAG_MARKET`, `RAG_NEWS`, `RAG_TRADES`;
- LightRAG ALGO KB отвечает по точному запросу к compact digest;
- естественные запросы к LightRAG все еще нестабильны, поэтому прямой LightRAG не возвращался в live decision path.

## Важное решение

LightRAG не добавлен обратно в каждый live-запуск трейдера.

Причина: это снова может увеличить задержку, стоимость и шум в prompt. Текущий live-путь остается таким:

- компактный `MKT`;
- компактный Qdrant RAG;
- полный `market_features` только для risk engine.

ALGO LightRAG теперь наполняется как trader-facing долговременная база, а не как прямой обязательный источник каждого решения.

## Следующие доработки

1. Улучшить `ref.instrument.news_keywords` для всех активных тикеров.
2. Добавить отдельный отчет качества RAG: coverage новостей, доля keyword match, возраст market snapshots.
3. Протестировать, какой режим LightRAG (`naive`, `local`, `hybrid`) лучше отвечает на compact digest.
4. Если возвращать LightRAG в live-контекст, делать только через кешированный короткий блок раз в 30-60 минут, не в каждом запуске трейдера.
