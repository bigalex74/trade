# Сжатие prompt трейдеров

Дата: 2026-04-23

Ветка изменения: `TRADE-006`

Версия проекта после изменения: `0.3.0`

## Причина

После включения RAG и расширения рыночного контекста успешные prompt трейдеров часто были около `7200-7900` символов.

Это уже не только риск превышения лимита. Большой вход повышает вероятность, что модель начнет путаться в данных и переоценивать второстепенные сигналы.

## Что изменено

### Разделение данных для ИИ и risk engine

Полный `market_features` остается для risk engine и исполнения заявок.

Для модели теперь строится отдельный компактный блок:

```text
MKT={...}
```

Это важно: мы уменьшаем шум для ИИ, но не ухудшаем риск-фильтры.

### Компактный контракт `MKT`

Добавлена функция:

```text
compact_prompt_market_payload()
```

Она:

- убирает длинное имя эмитента;
- сокращает ключи;
- переводит тренды в короткие значения `up/down/range/panic/mix`;
- переводит ликвидность в `H/M/L/U`;
- округляет числа;
- убирает ложные boolean-флаги;
- оставляет sentiment-текст только при заметном sentiment-score.

Пример смыслов:

```text
m5/h1/d1 - изменение за 5 минут, час, день
v5/vh - объемный ratio
vw - отклонение от VWAP
atr - ATR в процентах
liq - ликвидность
sent - sentiment-score
```

### Новый target prompt

Жесткий лимит остался:

```text
AI_PROMPT_MAX_CHARS_TRADER=8000
```

Но появился целевой размер:

```text
AI_PROMPT_TARGET_CHARS_TRADER=5200
```

Трейдер старается ужаться до target, а не просто не пробить hard-limit.

### Меньше тикеров по умолчанию

Было:

```text
AI_TRADER_MAX_SYMBOLS=8
```

Стало:

```text
AI_TRADER_MAX_SYMBOLS=6
AI_TRADER_MIN_SYMBOLS=4
```

Отбор тикеров остался приоритетным: быстрые трейдеры получают больше быстрых движений, медленные - больше ликвидности и дневного движения.

### RAG стал компактнее

Было:

```text
AI_RAG_SETUPS_LIMIT=3
AI_RAG_NEWS_LIMIT=3
AI_RAG_MAX_CHARS=700
```

Стало:

```text
AI_RAG_SETUPS_LIMIT=2
AI_RAG_NEWS_LIMIT=2
AI_RAG_MAX_CHARS=420
```

Формат RAG также сокращен:

```text
RAG_TRADES
RAG_NEWS
```

RAG снова помещается в prompt, но не доминирует над рыночными данными.

### Убрана устаревшая инструкция

Из prompt удалена инструкция:

```text
Query 'lightrag-algo'
```

Gemini CLI запускается без MCP, поэтому эта инструкция была шумом и могла путать модель.

## Проверенные результаты

Dry-run `Scalper_Kesha` с RAG:

```text
Market features: 6 тикеров, 1905 chars
Prompt market features: 1207 chars
Hybrid RAG: 2 сделки, 2 новости, 420 chars
Prompt chars: 2697 target=5200 limit=8000
```

Dry-run `Meta_Oracle` с RAG:

```text
Market features: 6 тикеров, 2012 chars
Prompt market features: 1377 chars
Hybrid RAG: 2 сделки, 2 новости, 420 chars
Prompt chars: 3871 target=5200 limit=8000
```

То есть RAG не отключается, а prompt стал существенно короче.

## Тесты

Добавлен:

```bash
tests/run_prompt_compaction_smoke.sh
```

Тест проверяет:

- компактный market payload реально меньше полного;
- число тикеров не меняется при compact-преобразовании;
- реальный dry-run `Scalper_Kesha` держит prompt ниже `5200`.

Также пройдены:

- `tests/run_tuning_phase1_phase2_smoke.sh`
- `tests/run_tuning_phase3_phase4_smoke.sh`
- `tests/run_tuning_phase5_phase9_smoke.sh`
- `tests/run_hybrid_rag_smoke.sh`
- `tests/run_ai_fallback_smoke.sh`

## Операционный вывод

RAG не отключен. Наоборот, после сжатия он снова стабильно помещается в prompt.

Главное изменение: модель теперь получает меньше шума и более структурированный вход, а risk engine продолжает работать на полном наборе данных.

Документ относится к общей технической базе знаний `https://kb.bigalexn8n.ru`.

В трейдерскую базу `https://algo.bigalexn8n.ru` документ не загружается.
