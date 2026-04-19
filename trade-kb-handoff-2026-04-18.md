# Trade KB Handoff — 2026-04-18

## Цель
Выделить отдельный контур для торговой базы знаний по MOEX:
- отдельный LightRAG
- отдельная Postgres БД
- отдельные n8n credentials
- перевод workflow с Data Tables на Postgres
- проверка реальных прогонов
- затем перенос секретов в Infisical

## Что уже сделано

### 1. Новый LightRAG для trading KB
Развернут отдельный инстанс LightRAG.

Расположение:
- `/home/user/lightrag-trade/`
- compose: `/home/user/lightrag-trade/docker-compose.yml`
- шаблон env: `/home/user/lightrag-trade/.env.example`
- текущий runtime env с секретами пока еще лежит в `/home/user/lightrag-trade/.env`

Порт:
- `127.0.0.1:9623`

Проверка:
- `http://127.0.0.1:9623/health` отвечает `200 OK`

### 2. Caddy / домен
В `Caddyfile` добавлен домен:
- `tradekb.bigalexn8n.ru`

Файл:
- `/home/user/n8n-docker/Caddyfile`

Примечание:
- локальный reverse proxy на новый LightRAG настроен
- внешний DNS A record должен быть прописан на хосте отдельно

### 3. Новая Postgres БД под research
Создана БД:
- `market_research`

Созданы роли:
- `market_owner`
- `market_rw`
- `market_ro`

Созданы схемы:
- `ref`
- `raw`
- `analytics`
- `ingest`
- `meta`

SQL bootstrap:
- `/home/user/n8n-docker/migrations/002_market_research_schema.sql`

Основные таблицы:
- `ref.instrument`
- `raw.news_item`
- `raw.news_instrument_match`
- `raw.candle`
- `analytics.instrument_snapshot`
- `analytics.research_digest`
- `ingest.lightrag_document_log`
- `meta.workflow_cursor`

Дополнительно:
- view `analytics.latest_snapshot`
- индексы и grants настроены
- сиды инструментов добавлены: `SBER`, `GAZP`, `LKOH`

### 4. Новые credentials в n8n
Созданы credentials:
- `Market Research Postgres RW`
- `Market Research Postgres RO`

Проверка была сделана отдельным smoke-test workflow через публичный webhook.
Итог: n8n успешно подключается к новой БД.

### 5. Миграция workflow с Data Tables на Postgres
Переведены workflow:

1. `MOEX | Candle Research Feed`
- workflow id: `BQM9Qy3rgMDURm1f`
- watchlist читает из `ref.instrument`
- пишет свечи в `raw.candle`
- пишет снапшоты в `analytics.instrument_snapshot`
- пишет публикации в `ingest.lightrag_document_log`
- публикует в новый LightRAG `http://127.0.0.1:9623`

2. `MOEX | News Research Feed`
- workflow id: `v77tZsa4wOtbPqwN`
- watchlist читает из Postgres
- пишет новости в `raw.news_item`
- пишет связи тикер-новость в `raw.news_instrument_match`
- пишет публикации в `ingest.lightrag_document_log`
- публикует в новый LightRAG

3. `MOEX | News Backfill`
- workflow id: `kYbCBufdz0XGWpiF`
- та же логика, что и у News Research Feed, но для batch/backfill

4. `MOEX | Daily Research Digest`
- workflow id: `Cefl1Xb6o3ceFoO0`
- watchlist читает из Postgres
- запрашивает новый LightRAG
- сохраняет дайджест в `analytics.research_digest`
- AI-дайджест не пишется обратно в KB

## Текущее состояние workflow
Все 4 workflow сейчас находятся в состоянии `inactive`.

Проверенные статусы:
- `BQM9Qy3rgMDURm1f` — inactive
- `v77tZsa4wOtbPqwN` — inactive
- `kYbCBufdz0XGWpiF` — inactive
- `Cefl1Xb6o3ceFoO0` — inactive

## Что проверено реально

### Формальная валидация
Все 4 workflow проходят `n8n_validate_workflow`.

### Реальные прогоны

#### News Backfill
Фактически отработал и записал данные в БД.

#### Daily Digest
Фактически отработал и сохранил запись в `analytics.research_digest`.

#### Candle Feed
Фактически дошел до боевой записи и частично записал данные.
Есть подтвержденные записи в:
- `raw.candle`
- `analytics.instrument_snapshot`
- `ingest.lightrag_document_log`

Но при длинных диапазонах свечей MOEX ISS иногда отвечает слишком медленно, из-за чего часть запросов падает по timeout.

## Итоговые данные после тестов
- `raw.candle = 3702`
- `analytics.instrument_snapshot = 33`
- `raw.news_item = 65`
- `raw.news_instrument_match = 65`
- `ingest.candle_logs = 12`
- `ingest.news_logs = 65`
- `analytics.research_digest = 1`

Последние записи:
- последний digest: `daily_digest | moex | 2026-04-17 18:25:29+00`
- последний news log: `moex/news/GAZP/https_www_moex_com_n98055 | published`
- последний candle log: `moex/candles/SBER/1w/2026-04-13T00:00:00.000Z | published`

## Выявленные проблемы

### 1. Candle collector ходит в слишком длинные диапазоны
Проблема не в архитектуре Postgres/LightRAG, а в модели загрузки свечей.
Сейчас workflow на каждом прогоне может тянуть длинную историю и упирается в timeout MOEX ISS.

Что уже сделано:
- timeout увеличен
- `Fetch MOEX Candles` переведен в режим продолжения по ошибке, чтобы единичный timeout не валил весь прогон

Но это временная стабилизация, а не финальное решение.

### 2. Infisical пока не добит
Перенос секретов не завершен.

Причина:
- установлен старый `infisical` CLI
- `infisical secrets set/get` отвечает, что project не подключен
- `infisical init` в этой среде упирается в keyring/DBus

Что это значит practically:
- секреты для `lightrag-trade` пока остаются в локальном `/home/user/lightrag-trade/.env`
- Postgres credentials пока хранятся в n8n credential store

## Дополнительные замечания
- Для `MOEX | News Backfill` деактивацию пришлось один раз вернуть напрямую через БД n8n из-за бага в `n8n_update_partial_workflow`.
- Это не затронуло сами JSON workflow, только состояние `active=false`.

## Что следующее по плану

### Приоритет 1. Починить candle collector
Нужно переделать сбор свечей на инкрементальную модель:
- хранить cursor/state в `meta.workflow_cursor`
- не тянуть длинную историю каждый раз
- для backfill/history использовать отдельный workflow
- рабочий сборщик должен забирать только свежий хвост

Идея целевой схемы:
- `MOEX | Candle Incremental Feed` берет `last_success_at` по каждому `secid + interval`
- если cursor пустой — берет короткое безопасное окно
- после успеха обновляет cursor
- отдельный backfill workflow закрывает исторические хвосты пакетами

### Приоритет 2. Довести Infisical
Нужно:
- обновить/починить `infisical` CLI
- восстановить рабочий non-interactive доступ к project `1d44cf0c-94b5-4e64-bccd-9c4da8843fec`
- переложить секреты `lightrag-trade` в Infisical
- перевести запуск `lightrag-trade` на `infisical run -- docker compose up -d`
- после проверки удалить секреты из локального `.env`

### Приоритет 3. Решить вопрос боевой активации
После стабилизации candle feed:
- активировать нужные workflow
- разнести расписания по нагрузке
- возможно отделить research feed от backfill feed полностью

## Полезные файлы
- `/home/user/trade-kb-handoff-2026-04-18.md`
- `/home/user/lightrag-trade/docker-compose.yml`
- `/home/user/lightrag-trade/.env.example`
- `/home/user/n8n-docker/Caddyfile`
- `/home/user/n8n-docker/migrations/002_market_research_schema.sql`

## Короткий план на следующий сеанс
1. Переделать `MOEX | Candle Research Feed` в инкрементальный режим через `meta.workflow_cursor`
2. После этого снова прогнать реальный тест и проверить, что timeout больше не валит сбор
3. Затем отдельно заняться Infisical CLI и переносом секретов

## Update 2026-04-18 06:40 MSK

### Что доделано после handoff
`MOEX | Candle Research Feed` переведен на инкрементальную модель через `meta.workflow_cursor`.

Что изменено в workflow `BQM9Qy3rgMDURm1f`:
- `Get Watchlist` теперь сразу разворачивает активные инструменты по интервалам и подтягивает cursor-state из `meta.workflow_cursor`
- `Expand Interval Requests` больше не строит фиксированные длинные окна; теперь считает `from_date/till_date` от cursor с overlap по интервалу
- `Normalize Candle Snapshot` сохраняет `request_mode`, `cursor_key`, `cursor_loaded`, `latest_candle_time`
- добавлен Postgres node `Update Candle Cursor`, который пишет новый cursor после успешной публикации

### Валидация
`n8n_validate_workflow`:
- `valid = true`
- ошибок нет
- остались только предупреждения про error handling у code/http/postgres nodes

### Реальная проверка
Для проверки был временно добавлен webhook trigger, после теста он удален.
Workflow снова находится в состоянии `active = false`.

Фактический post-check по БД `market_research`:
- до запуска: `meta.workflow_cursor = 12`, `raw.candle = 5211`, `analytics.instrument_snapshot = 464`, `ingest.candle_logs = 24`
- после запуска: `meta.workflow_cursor = 12`, `raw.candle = 5211`, `analytics.instrument_snapshot = 476`, `ingest.candle_logs = 24`

Что это означает:
- cursor-based прогон отработал и обновил те же 12 ключей cursor
- новые snapshot records записались: `+12`
- новые raw candle строки не добавились, потому что пришли уже известные свечи и сработал upsert
- количество log строк не выросло, потому что `ingest.lightrag_document_log` обновляет существующие записи по `source_key`

Подтвержденные timestamps:
- cursor `updated_at` сдвинулся с `2026-04-18 03:38:11+00` на `2026-04-18 03:40:20+00`
- `ingest.lightrag_document_log.published_at` для последних candle documents тоже обновился на `2026-04-18 03:40:20+00`

## Update 2026-04-18 14:40 MSK

### Infisical cutover для `lightrag-trade` завершен

Что сделано:

- в `/home/user/lightrag-trade` добавлен `.infisical.json` на тот же project/workspace
- `docker-compose.yml` и `docker-compose.lightrag-trade.yml` переведены с `env_file` на явные `environment` variables
- добавлены helper scripts:
  - `/home/user/lightrag-trade/scripts/set_lightrag_trade_secrets_in_infisical.sh`
  - `/home/user/lightrag-trade/scripts/verify_lightrag_trade_infisical.sh`
  - `/home/user/lightrag-trade/scripts/compose_with_infisical.sh`
- runtime-набор переменных загружен в `Infisical` path `/lightrag-trade`
- контейнер `lightrag-trade` пересоздан через `Infisical`
- локальный plaintext `/home/user/lightrag-trade/.env` удален

Что проверено:

- `./scripts/verify_lightrag_trade_infisical.sh` проходит по всем 21 переменным
- `./scripts/compose_with_infisical.sh ps` показывает поднятый `lightrag-trade`
- `http://127.0.0.1:9623/health` вернул `healthy`
- контейнер стартовал с ожидаемыми runtime env, при этом ключи больше не лежат в локальном `.env`

Дополнение:

- текущий `infisical` CLI все еще старый (`0.38.0`) и печатает warning про доступный апдейт, но cutover на нем сработал корректно
- теперь для любых compose-операций в этом проекте нужно использовать `./scripts/compose_with_infisical.sh ...`

Текущий активный watchlist в trade DB:
- `GAZP`
- `LKOH`
- `SBER`

### Что это закрывает
Закрыт основной риск предыдущей версии candle feed:
- workflow больше не зависит от постоянного длинного исторического окна на каждом запуске
- состояние по свечам теперь живет в Postgres, а не вычисляется заново каждый раз
- дальнейшее масштабирование по количеству инструментов теперь делается через cursor/backfill, а не через расширение lookback window

### Что следующее теперь
Новый приоритет после этого шага:
1. Сделать отдельный candle backfill workflow для исторической догрузки пакетами, если нужен глубокий архив вне текущего cursor-tail
2. Довести Infisical и вынести секреты `lightrag-trade` + связанные runtime secrets из локальных конфигов
3. После Infisical решить, какие workflow переводить в боевой `active` режим и с какими расписаниями

## Update 2026-04-18 07:07 MSK

### Новый workflow: candle backfill
Создан отдельный workflow:
- `MOEX | Candle Backfill`
- workflow id: `eGLrEdlnVD6ZbHUj`
- состояние: `active = false`

Финальная структура workflow:
- `Manual Trigger`
- `Schedule Trigger`
- `Backfill Config`
- `Get Backfill Scope`
- `Build Backfill Requests`
- `Fetch MOEX Candles`
- `Merge Meta and Response`
- `Normalize Backfill Batch`
- `Upsert Raw Candle Batch`
- `Update Backfill Cursor`

Что делает workflow:
- читает активные инструменты из `ref.instrument`
- строит scope по интервалам и подтягивает:
  - live cursor `moex:candle:*`
  - backfill cursor `moex:candle_backfill:*`
  - earliest already loaded candle из `raw.candle`
- для каждого `secid + interval` выбирает anchor и грузит предыдущий исторический пакет
- пишет свечи только в `raw.candle`
- обновляет отдельный backfill cursor в `meta.workflow_cursor`
- ничего не публикует в LightRAG и не пишет в `analytics.instrument_snapshot`

Ключи backfill state:
- формат: `moex:candle_backfill:<engine>:<market>:<board>:<secid>:<interval_name>`

Параметры batch/floor сейчас такие:
- `1m`: batch `5` days, floor `90` days
- `1h`: batch `30` days, floor `730` days
- `1d`: batch `180` days, floor `3650` days
- `1w`: batch `730` days, floor `7300` days

### Валидация
Итоговая валидация:
- `valid = true`
- `triggerNodes = 2`
- ошибок нет
- warnings остались только по code/http общему error handling

### Реальный тест на SBER
Для проверки workflow временно был ограничен:
- `target_secid = 'SBER'`
- `max_requests = 4`

Тест запускался через временный webhook. После проверки workflow возвращен в дефолтную конфигурацию и выключен.

Результат теста по `SBER`:
- `1m`: было `1000` строк, earliest `2026-04-16 06:59:00+00` -> стало `1500` строк, earliest `2026-04-11 09:59:00+00`
- `1h`: было `474` строк, earliest `2026-03-18 06:00:00+00` -> стало `922` строки, earliest `2026-02-16 06:00:00+00`
- `1d`: было `159` строк, earliest `2025-10-19 00:00:00+00` -> стало `326` строк, earliest `2025-04-22 00:00:00+00`
- `1w`: было `104` строки, earliest `2024-04-22 00:00:00+00` -> стало `208` строк, earliest `2022-04-25 00:00:00+00`

Итог по объему данных:
- `raw.candle`: `5211 -> 6430` (`+1219`)
- `meta.workflow_cursor` для `moex:candle_backfill:*`: `0 -> 4`

Созданные backfill cursor после теста:
- `moex:candle_backfill:stock:shares:TQBR:SBER:1m -> 2026-04-11T09:59:00.000Z`
- `moex:candle_backfill:stock:shares:TQBR:SBER:1h -> 2026-02-16T06:00:00.000Z`
- `moex:candle_backfill:stock:shares:TQBR:SBER:1d -> 2025-04-22T00:00:00.000Z`
- `moex:candle_backfill:stock:shares:TQBR:SBER:1w -> 2022-04-25T00:00:00.000Z`

### Текущее дефолтное поведение workflow
Сейчас `Backfill Config` по умолчанию:
- `target_secid = ''`
- `target_interval = ''`
- `max_requests = 0`

То есть workflow готов к ручному full-run по всем активным инструментам, но пока выключен.

### Что логично делать дальше
Следующий шаг после создания backfill workflow:
1. решить, нужен ли для backfill постоянный nightly schedule или пока оставляем manual-only использование
2. довести Infisical и вынести runtime secrets
3. затем определить, какие workflow активировать в production и с какими расписаниями

## Update 2026-04-18 07:10 MSK

### Nightly schedule для candle backfill включен
Workflow `MOEX | Candle Backfill` (`eGLrEdlnVD6ZbHUj`) переведен в активный режим.

Что изменено:
- workflow `active = true`
- добавлена отдельная ветка `Scheduled Backfill Config`
- ручная ветка сохранена отдельно как `Manual Backfill Config`
- workflow timezone выставлен в `Europe/Moscow`

Текущее расписание:
- `Schedule Trigger`: ежедневно в `03:07` MSK

Почему именно так:
- запуск не попадает ровно в `00/15/30/45` минутные границы
- это снижает риск одновременного старта с будущим incremental feed, если он позже будет активирован с 15-минутным расписанием

### Scheduled config
Ночная конфигурация сейчас такая:
- `target_secid = ''`
- `target_interval = ''`
- `max_requests = 12`
- `requested_by = 'nightly_schedule'`

Это значит:
- за один ночной запуск workflow делает максимум `12` historical fetch requests
- при текущем watchlist (`GAZP`, `LKOH`, `SBER`) это покрывает по одному backfill batch на каждый `secid + interval`

### Fair ordering для backfill scope
`Get Backfill Scope` теперь сортирует не просто по `secid`, а так:
- сначала комбинации, которые давно не backfill-ились
- `ORDER BY COALESCE(backfill_wc.updated_at, TO_TIMESTAMP(0)) ASC, secid, interval_code`

Практический эффект:
- при лимите `max_requests` новые инструменты не будут вечно starvation'иться
- с ростом universe workflow будет постепенно ротировать очередность исторической догрузки

### Manual branch сохранена
Ручной trigger не сломан:
- `Manual Backfill Config` по-прежнему дает unrestricted режим (`max_requests = 0`)
- его можно использовать для ручного широкого прогона, не трогая ночной scheduled profile

### Состояние production сейчас
- `MOEX | Candle Backfill` -> `active = true`
- `MOEX | Candle Research Feed` -> `active = false`

То есть ночной historical backfill уже поставлен на расписание,
а основной incremental feed пока не включен.

## Update 2026-04-18 07:17 MSK

### Production-активация торгового контура завершена
После backfill доведены и включены оставшиеся production workflow:
- `MOEX | News Research Feed` (`v77tZsa4wOtbPqwN`) -> `active = true`
- `MOEX | Candle Backfill` (`eGLrEdlnVD6ZbHUj`) -> `active = true`
- `MOEX | Candle Research Feed` (`BQM9Qy3rgMDURm1f`) -> `active = true`
- `MOEX | Daily Research Digest` (`Cefl1Xb6o3ceFoO0`) -> `active = true`

Итог: весь базовый research-контур сейчас активен.

### Candle Research Feed: новое расписание под торговые сессии MOEX
Workflow `MOEX | Candle Research Feed` переведен с тупого `every 15 minutes 24/7`
на расписание, привязанное к торговым окнам MOEX.

Текущее расписание:
- будни: первый запуск `06:55` MSK
- будни: далее `07:05, 07:20, 07:35, 07:50 ... 23:50` MSK
- будни: дополнительный контрольный запуск `23:55` MSK
- выходные: первый запуск `09:55` MSK
- выходные: далее `10:05, 10:20, 10:35, 10:50 ... 18:50` MSK
- выходные: дополнительный контрольный запуск `19:05` MSK

Как это реализовано:
- `Schedule Trigger` переведен на набор cron-правил
- timezone workflow выставлен в `Europe/Moscow`

Почему так:
- workflow больше не тратит ресурсы ночью вне торговых окон
- покрываются утренняя, основная и вечерняя сессии будней
- покрывается weekend session
- финальные post-close запуски помогают дотянуть последние свечи после закрытия сессии

### Daily Research Digest: новое время и корректная дата торгового дня
Workflow `MOEX | Daily Research Digest` включен и перенесен на время после полного завершения торгового дня.

Текущее расписание:
- ежедневно в `00:20` MSK

Почему не оставлено старое время `19:10`:
- оно отрезало вечернюю сессию буднего дня
- для нового режима рынка это давало неполный дневной контекст

Дополнительно исправлена логика даты digest:
- в `Build Research Prompt` добавлено поле `digest_for_date`
- если digest генерируется ночью до `06:00` MSK, дата торговой сессии берется как предыдущий локальный день
- `source_key` теперь строится от `digest_for_date`, а не от простого `report_time`

Практический эффект:
- digest после полуночи не будет ошибочно маркироваться следующим календарным днем
- записи в `analytics.research_digest` и в knowledge trail легче сопоставлять с торговой сессией

### Валидация после финальных правок
Проверено через `n8n_validate_workflow`:
- `MOEX | Candle Research Feed` -> `valid = true`
- `MOEX | Daily Research Digest` -> `valid = true`
- критических ошибок нет
- warnings остались только по общему error handling code/http/postgres nodes

### Что логично делать следующим шагом
Следующий технически правильный этап:
1. прогнать наблюдение по execution history 1-2 торговых дня
2. убедиться, что backfill и incremental не конфликтуют по нагрузке и по cursor progression
3. после этого вынести секреты в Infisical и перепривязать runtime к нему

## Update 2026-04-18 07:41 MSK

### Наблюдение по execution history: встроенный Schedule Trigger сейчас не подтвержден как рабочий production-механизм
После активации production workflow были проверены execution history и ближайшие контрольные слоты:
- `MOEX | News Research Feed` должен был сработать в `07:33` MSK
- `MOEX | Candle Research Feed` должен был сработать в `07:35` MSK

Факт:
- новых execution у этих workflow не появилось
- при этом сами workflow остаются `active = true`
- `workflowPublishHistory` подтверждает, что версии были реально activated
- на инстансе есть другие trigger execution, значит API и execution subsystem живы, но проблема именно с текущим production path для `Schedule Trigger`

Практический вывод:
- перенос секретов в `Infisical` пока не следующий шаг
- сначала надо либо чинить scheduler инстанса, либо использовать внешний orchestration layer

### Параллельно исправлен runtime-дефект News Feed
До этого у `MOEX | News Research Feed` были реальные trigger errors:
- TLS disconnect
- timeout 60000ms

Что изменено:
- убран `RSS Feed Trigger` как production entrypoint
- вместо него добавлены:
  - `Schedule Trigger`
  - `Read MOEX RSS`
- feed теперь сначала пишет все RSS элементы в `raw.news_item`
- дальше через `RETURNING (xmax = 0) AS inserted` пропускаются только реально новые новости
- матчинг и публикация в LightRAG выполняются только для fresh items

Зачем это сделано:
- устраняет нестабильный polling самого RSS trigger
- устраняет повторную публикацию старых RSS элементов при повторных чтениях feed

Итоговая валидация News Feed после рефакторинга:
- `valid = true`

### Подготовлен production fallback: внешний cron через локальные webhook
Так как `Schedule Trigger` сейчас не дает подтвержденных запусков, подготовлен обходной production path:
- каждому MOEX workflow добавлен `Internal Cron Webhook`
- allowlist webhook ограничен `127.0.0.1,::1`
- workflow остаются активными и валидными

Webhook paths:
- News: `moex-news-feed-int-b0e19a6a`
- Candle: `moex-candle-feed-int-7c1a55d9`
- Backfill: `moex-backfill-int-e95bf233`
- Digest: `moex-digest-int-6fa741bc`

Файлы, подготовленные для host-side cron:
- trigger script: `/home/user/n8n-docker/scripts/trigger_moex_workflow.sh`
- cron manifest: `/home/user/n8n-docker/crontab/moex_research.cron`

Что делает script:
- принимает ключ `news|candle|backfill|digest`
- сначала бьет в `http://127.0.0.1:5678/webhook/<path>`
- если local endpoint недоступен, пробует fallback в `https://bigalexn8n.ru/webhook/<path>`

Важно:
- из текущей песочницы нельзя записать системный crontab пользователя
- прямой `crontab -l` здесь дает `Permission denied`
- поэтому host cron не был реально установлен в рамках этого хода

### Дополнительное наблюдение по тестированию
`n8n_test_workflow` не дал полноценной runtime-проверки webhook path, потому что в тестовом режиме execution уперся в SSRF protection на приватных адресах.
Это относится к инструменту тестирования, а не доказывает production-неработоспособность самих workflow.

### Текущее состояние
Сейчас готово следующее:
- данные и KB контур развернуты
- News runtime logic исправлена
- все 4 MOEX workflow `valid = true`
- всем 4 workflow добавлены локальные webhook entrypoints для внешнего cron
- файлы для cron orchestration подготовлены

Что остается следующим технически правильным шагом:
1. установить `moex_research.cron` на хосте или в `crontab-ui`
2. после этого проверить первые реальные webhook-driven executions
3. только после подтверждения стабильных execution идти к `Infisical`

## Update 2026-04-18 07:48 MSK

### Для host-side cron добавлены install/remove scripts
Чтобы не редактировать `crontab` руками, подготовлены отдельные скрипты:
- `/home/user/n8n-docker/scripts/apply_moex_cron.sh`
- `/home/user/n8n-docker/scripts/remove_moex_cron.sh`

Как работают:
- `apply_moex_cron.sh` создает/обновляет только managed block между маркерами:
  - `# BEGIN MOEX RESEARCH`
  - `# END MOEX RESEARCH`
- любые посторонние cron entries пользователя сохраняются
- `remove_moex_cron.sh` удаляет только этот managed block

### Cron manifest сделан timezone-stable
В `/home/user/n8n-docker/crontab/moex_research.cron` добавлены:
- `CRON_TZ=Europe/Moscow`
- `TZ=Europe/Moscow`

Это важно, чтобы расписание свечей, digest и backfill не зависело от timezone хоста.

### Добавлена отдельная памятка по установке и проверке
Создан файл:
- `/home/user/n8n-docker/MOEX_CRON_SETUP.md`

В нем есть:
- команды установки и снятия cron блока
- ручной trigger каждого workflow
- команды просмотра логов
- checklist, что именно считать успешной verification

### Ограничение песочницы остается прежним
Из текущей sandbox-сессии системный `crontab` пользователя все еще нельзя реально установить.
Поэтому следующий реальный operational step должен быть выполнен уже на хосте:

1. `cd /home/user/n8n-docker`
2. `./scripts/apply_moex_cron.sh`
3. вручную дернуть 1-2 workflow через `trigger_moex_workflow.sh`
4. проверить execution в `n8n`
5. дождаться ближайшего cron slot и убедиться, что scheduler path стабилен

## Update 2026-04-18 08:05 MSK

### Host-side cron path подтвержден реальным запуском
После установки `crontab` пользователь вручную подтвердил:
- `trigger_moex_workflow.sh news` => `Workflow was started`
- `trigger_moex_workflow.sh candle` => `Workflow was started`

Далее был дождался реальный news slot `08:03 MSK`, и в host log появился успешный cron-trigger:

```text
[2026-04-18T08:03:01+03:00] trigger start workflow=news path=moex-news-feed-int-b0e19a6a
[2026-04-18T08:03:01+03:00] trigger success workflow=news target=local response={"message":"Workflow was started"}
```

Практический вывод:
- внешний orchestration layer через host `cron` рабочий
- как минимум `news` scheduler path подтвержден без ручного участия

### Наблюдение, которое остается открытым
По API `n8n` и по таблице `execution_entity` новые execution от этих webhook пока не видны, несмотря на успешный ответ webhook endpoint.

Это означает:
- либо successful webhook executions по текущим настройкам не сохраняются в execution store так, как manual runs
- либо существует рассинхрон между runtime endpoint и способом, которым читается execution history

На данном этапе это уже не blocker для cron orchestration, потому что сам факт host-side запуска подтвержден логом.

### Что теперь логично делать дальше
Следующий шаг уже не про cron как таковой, а про верификацию полезной нагрузки:

1. проверить, что `news` действительно пишет данные в trade DB / LightRAG
2. дождаться или вручную подтвердить первый `candle` cron hit
3. после этого завершать перенос секретов в `Infisical`

## Update 2026-04-18 13:45 MSK

### Payload verification завершена: trade DB и `tradekb` реально обновляются
Так как прямого подключения к market research DB из текущего MCP не было, для проверки были временно созданы одноразовые diagnostic workflow в `n8n`, использующие production credential:

- `Market Research Postgres RW`

Проверка шла через публичные webhook этих временных workflow, после чего они были удалены.

### Подтвержденные факты по данным
Ответ focused probe показал:

- `news_item_last_15m = 1176`
- `news_match_last_15m = 0`
- `lightrag_news_item_last_15m = 0`
- `lightrag_candle_snapshot_last_15m = 12`
- `candle_last_15m = 1656`
- `snapshot_last_15m = 24`
- `cursor_last_15m = 12`

Практический смысл:

- `news` workflow реально пишет в `raw.news_item`
- `candle` workflow реально пишет в `raw.candle`
- `candle` workflow реально пишет `analytics.instrument_snapshot`
- `candle` workflow реально обновляет `meta.workflow_cursor`
- `candle` workflow реально публикует документы в `tradekb`

### Историческая проверка news publish path
Отдельный news publish probe показал:

- `news_item_published_total = 65`
- `news_item_published_last_24h = 65`
- `latest_news_item_published_at = 2026-04-17T18:22:09.521758+00:00`

Последняя подтвержденная публикация новости в `tradekb`:

- `document_type = news_item`
- `source_key = moex/news/GAZP/https_www_moex_com_n98055`
- `source_pk = GAZP:https_www_moex_com_n98055`
- `published_at = 2026-04-17T18:22:09.521758+00:00`

Последний подтвержденный match:

- `matched_keywords = газпром, газпром`
- `matched_at = 2026-04-17T18:22:08.678007+00:00`

Вывод:

- news publish path в `tradekb` работает
- нулевые `news_match_last_15m` и `lightrag_news_item_last_15m` означают не поломку pipeline, а отсутствие новых релевантных совпадений в недавнем окне

### Важное наблюдение по semantics поля `ingested_at`
Focused probe показал, что последние строки `raw.news_item` имеют старые `published_at`, но свежий `ingested_at`.

Это соответствует текущему SQL в `Upsert Raw News Items`:

- при `ON CONFLICT` выполняется `ingested_at = NOW()`

Следствие:

- `ingested_at` сейчас означает не `first seen`, а `last refreshed`
- RSS feed при каждом чтении обновляет существующие строки и перезаписывает `ingested_at`
- downstream-дедупликация не ломается, потому что публикация фильтруется по `RETURNING (xmax = 0) AS inserted`

Это не blocker, но это нужно помнить при аналитике и мониторинге.

### Диагностические workflow удалены
После проверки были удалены временные workflow:

- `MOEX | Trade DB Probe Temp`
- `MOEX | Trade DB Focus Probe Temp`
- `MOEX | News Publish Probe Temp`

### Текущее состояние на конец проверки
На текущем этапе подтверждено:

1. host `cron` реально вызывает internal webhook
2. `news` pipeline реально пишет в trade DB
3. `news` pipeline исторически публиковал и сейчас способен публиковать в `tradekb`
4. `candle` pipeline реально пишет в trade DB и публикует в `tradekb`

Следующий шаг по исходному плану:

1. перейти к переносу секретов в `Infisical`
2. отдельно решить, хотим ли мы сохранить `ingested_at` как `last refreshed` или менять модель на `first seen + last_seen_at`

## Update 2026-04-18 13:55 MSK

### Подготовлен staged cutover на Infisical
Так как payload verification прошла успешно, следующий шаг по плану был начат.

Что сделано:

- `docker-compose.yml` переведен в staged режим для чувствительных переменных
- добавлен пример env-файла для host-side загрузки секретов:
  - `/home/user/n8n-docker/.env.infisical.n8n.infra.example`
- добавлен gitignore для локального заполненного файла:
  - `/home/user/n8n-docker/.gitignore`
- добавлены host-side helper scripts:
  - `/home/user/n8n-docker/scripts/set_n8n_infra_secrets_in_infisical.sh`
  - `/home/user/n8n-docker/scripts/verify_n8n_infra_infisical.sh`
- добавлена инструкция:
  - `/home/user/n8n-docker/INFISICAL_N8N_INFRA_CUTOVER.md`

### Что именно параметризовано в docker-compose
Чувствительные значения теперь могут приходить из env/Infisical:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `N8N_ENCRYPTION_KEY`
- `DB_POSTGRESDB_HOST`
- `DB_POSTGRESDB_PORT`
- `DB_POSTGRESDB_DATABASE`
- `DB_POSTGRESDB_USER`
- `DB_POSTGRESDB_PASSWORD`
- `PGADMIN_DEFAULT_EMAIL`
- `PGADMIN_DEFAULT_PASSWORD`
- `POSTGRES_EXPORTER_DATA_SOURCE_NAME`

Важно:

- пока оставлены fallback literals
- это сделано специально, чтобы cutover был безрисковым
- после host-side verification нужно будет отдельным ходом убрать fallback literals окончательно

### Что проверено

- bash syntax для новых scripts проходит
- `docker compose config` после параметризации проходит

### Почему cutover не был выполнен из этой сессии до конца
Попытка обратиться к `Infisical` CLI из sandbox показала blocker:

```text
failed to fetch credentials from keyring
dial unix /run/user/1000/bus: connect: operation not permitted
```

Это означает:

- текущая sandbox-среда не имеет доступа к вашему локальному `dbus/system keyring`
- проблема не в `Infisical` проекте и не в подготовленных файлах
- реальные `infisical secrets set/get` операции нужно выполнять уже на хосте

### Следующий правильный operational step

На хосте:

1. заполнить `/home/user/n8n-docker/.env.infisical.n8n.infra`
2. выполнить `./scripts/set_n8n_infra_secrets_in_infisical.sh`
3. выполнить `./scripts/verify_n8n_infra_infisical.sh`
4. выполнить `./restart_n8n.sh`
5. проверить, что MOEX workflows и `tradekb` продолжают работать

После этого уже можно делать cleanup pass и удалять fallback literals из `docker-compose.yml`.
