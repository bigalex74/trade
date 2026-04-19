# AI Gateway — Проектная документация

**Дата:** 2026-04-12  
**Статус:** Проектирование  
**Автор:** Qwen Code (Prime Agent)

---

## 1. ТЕКУЩЕЕ СОСТОЯНИЕ (AS-IS)

### 1.1 AI-агенты и их LLM-зависимости

В системе **4 уникальных AI-агента** с прямыми LLM-вызовами. Каждый жёстко привязан к конкретным моделям и credential'ам внутри своего workflow.

| Агент | Workflow ID | LLM-ноды (встроенные) | Pattern |
|-------|-------------|----------------------|---------|
| **Переводчик** | `GPARI8V4RBSPL1h39_kHW` (34 узла) | `@n8n/n8n-nodes-langchain.agent` × 2 | Agent с fallback (index 0 = Neuro GPT-5.2, index 1 = Polza GPT-5.2). Fallback: Claude 4.5 (Neuro + Polza). |
| **Постредактор** | `A8zKJVQgROH1cnkv` (9 узлов) | `@n8n/n8n-nodes-langchain.agent` × 1 + 3 AI tools | Agent с fallback (Neuro GPT-5.2 → Polza GPT-5.3) + tools: text_validator (JS), parentheses_checker (JS), check_forbidden_words (PostgreSQL). |
| **Саммаризатор** | `IgLfaCSszdwsPw_b4u3au` (26 узлов) + `OggkJgA8IFmasME_BNimq` (31 узлов) | `@n8n/n8n-nodes-langchain.informationExtractor` × 5 | InformationExtractor (без fallback), модель Gemini 2.5 Flash Lite (Polza). Используется в Главе (rolling summary + chapter summary) и Арке (arc boundary + arc summary × 3). |
| **Аналитик** | `lSuNRX0VILP9Lgit5VKlK` (27 узлов) + `2kztTVutdATd1MDS` (7 узлов) | `@n8n/n8n-nodes-langchain.informationExtractor` × 2 + `@n8n/n8n-nodes-langchain.chainLlm` × 1 | InformationExtractor с fallback (OpenAI model 1 → OpenAI model 2). Анотация: OpenAI chain. |

### 1.2 Паттерны вызова LLM

**Паттерн A — Agent с fallback (Переводчик, Постредактор):**
```
Agent node → needsFallback: true
  ├── ai_languageModel[0] (primary): Neuro API, model=gpt-5.2-chat-latest
  └── ai_languageModel[1] (fallback): Polza API, model=openai/gpt-5.2-chat или openai/gpt-5.3-chat
```
При ошибке primary → автоматически fallback. Agent принимает `text` (user prompt) + `systemMessage`.

**Паттерн B — InformationExtractor (Саммаризатор, Аналитик):**
```
InformationExtractor node → no fallback в узле
  └── ai_languageModel[0]: Polza API, model=gemini-2.5-flash-lite
```
Извлекает структурированные данные (summary, arc boundaries). Не использует system prompt в том же виде, что Agent.

**Паттерн C — ChainLlm (Анотация):**
```
ChainLlm node
  └── ai_languageModel[0]: OpenAI API
```
Простой LLM chain для генерации текста (промт для картинки).

**Паттерн D — Agent с tools (Постредактор):**
```
Agent node → needsFallback: true
  ├── ai_languageModel[0]: Neuro GPT-5.2
  ├── ai_languageModel[1]: Polza GPT-5.3
  ├── ai_tool[0]: text_validator (JS code tool)
  ├── ai_tool[1]: parentheses_checker (JS code tool)
  └── ai_tool[2]: check_forbidden_words (PostgreSQL tool)
```

### 1.3 Модели и провайдеры

| Провайдер | Credential ID | Модели | Базовый URL |
|-----------|---------------|--------|-------------|
| **Neuro API** | `BsGSDSjRdNfiWliT` | gpt-5.2-chat-latest | Neuro API endpoint |
| **Polza.ai** | `dw2ygQ53RyVkCAva` | openai/gpt-5.2-chat, openai/gpt-5.3-chat, gemini-2.5-flash-lite | https://polza.ai/api/v1 |
| **Ollama** | (без credentials) | llama3.2:3b | http://127.0.0.1:11434 |

### 1.4 Проблема

Каждый workflow **хардкодит** модели и credentials на уровне node configuration. Для переключения на Ollama (E2E тест) нужно:
1. Дублировать каждый workflow
2. Менять LLM-ноды вручную
3. Поддерживать两套 конфигураций

---

## 2. ЦЕЛЕВАЯ АРХИТЕКТУРА (TO-BE)

### 2.1 Принципы

1. **Zero-downtime migration** — production-перевод на платных моделях работает ВСЕГДА, независимо от E2E тестов
2. **Единый интерфейс** — все AI-агенты вызываются через под-workflow с одинаковым входным/выходным контрактом
3. **Model-agnostic** — AI-агент НЕ знает, какая модель используется; модель выбирается на уровне Gateway
4. **Environment-based routing** — режим определяется переменной `AI_MODEL_MODE`:
   - `production` → платные модели (Neuro → Polza fallback)
   - `e2e-test` → бесплатные модели (Ollama llama3.2:3b)
5. **Isolated test runs** — E2E тесты НЕ влияют на production данные (отдельные job_id, separate DB records)

### 2.2 Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│                        AI GATEWAY                            │
│              [AI Gateway] Model Router                       │
│                                                              │
│  Вход:                                                       │
│    - agent_type: translator | posteditor | summarizer        │
│                  | arcanalyst | analyzer | annotator          │
│    - model_mode: production | e2e-test                       │
│    - inputs: { ko_text, ru_text, glossary, rag, ... }        │
│    - job_id (опционально, для E2E隔离)                         │
│                                                              │
│  Логика:                                                     │
│    1. Определяет agent_type → выбирает sub-workflow          │
│    2. Определяет model_mode → выбирает модель/credential     │
│    3. Вызывает sub-workflow через Execute Workflow node      │
│    4. Возвращает результат + метрики                          │
│                                                              │
│  Выход:                                                      │
│    - output: translated_text / summary / analysis            │
│    - model_used: "neuro/gpt-5.2" | "ollama/llama3.2:3b"      │
│    - latency_ms, tokens_estimated, fallback_used             │
│    - error: null | { message, retry_count }                  │
└────────────────────┬─────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────┬──────────┐
        │            │            │            │          │
   ┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌───▼────┐
   │Transl- │  │Post-   │  │Summ-   │  │Arc-    │  │Analyz- │
   │ator    │  │editor  │  │arizer  │  │alyst   │  │er      │
   │(Agent) │  │(Agent) │  │(InfoX) │  │(InfoX) │  │(InfoX) │
   └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
        │            │            │            │          │
        └────────────┴────────────┴────────────┴──────────┘
                     │
              ┌──────▼──────┐
              │ MODEL LAYER │
              │             │
              │ Production: │
              │  Neuro GPT  │
              │  Polza GPT  │
              │  Polza Gem  │
              │             │
              │ E2E Test:   │
              │  Ollama     │
              │  llama3.2   │
              └─────────────┘
```

### 2.3 Sub-workflow'ы агентов (6 отдельных workflow)

Каждый агент — отдельный workflow с `executeWorkflowTrigger`. Принимает стандартный вход + `model_mode`.

#### 2.3.1 `[AI Agent] Translator` — Переводчик

**Вход:**
```json
{
  "ko_text": "корейский текст чанка",
  "system_prompt": "сформированный системный промпт",
  "user_prompt": "сформированный пользовательский промпт",
  "model_mode": "production | e2e-test",
  "job_id": "идентификатор задачи"
}
```

**Логика:**
```
If model_mode == "production":
  → Primary: Neuro GPT-5.2 (credential: Neuroapi)
  → Fallback: Polza GPT-5.2 (credential: Polza)
  
If model_mode == "e2e-test":
  → Primary: Ollama llama3.2:3b
  → Fallback: Ollama llama3.2:3b (retry)
```

**Выход:**
```json
{
  "output": "переведённый текст",
  "model_used": "neuro/gpt-5.2-chat-latest",
  "fallback_used": false,
  "latency_ms": 3200
}
```

#### 2.3.2 `[AI Agent] Posteditor` — Постредактор

**Вход:**
```json
{
  "ko_text": "оригинал",
  "ru_text": "черновой перевод",
  "glossary": "текст глоссария",
  "rag": "контекст из RAG",
  "model_mode": "production | e2e-test"
}
```

**Логика:**
```
If model_mode == "production":
  → Primary: Neuro GPT-5.2
  → Fallback: Polza GPT-5.3
  → Tools: text_validator, parentheses_checker, check_forbidden_words
  
If model_mode == "e2e-test":
  → Primary: Ollama llama3.2:3b
  → Fallback: none (Ollama не поддерживает tools)
  → Tools: text_validator (JS), parentheses_checker (JS)
  → check_forbidden_words: выполняем CODE-нодой ПОСЛЕ agent
```

**Ключевое отличие:** В E2E-режиме AI tools через PostgreSQL не работают с Ollama (Ollama не поддерживает function calling). Инструменты выполняются как post-processing.

#### 2.3.3 `[AI Agent] Summarizer` — Саммаризатор (Глава)

**Вход:**
```json
{
  "text": "текст для summarization",
  "task": "rolling_summary | chapter_summary",
  "glossary": "глоссарий",
  "model_mode": "production | e2e-test"
}
```

**Логика:**
```
If model_mode == "production":
  → Gemini 2.5 Flash Lite (Polza) — informationExtractor
  
If model_mode == "e2e-test":
  → Ollama llama3.2:3b — Agent node (т.к. Ollama не поддерживает informationExtractor)
  → Промт адаптирован для структурированного вывода
```

#### 2.3.4 `[AI Agent] ArcAnalyst` — Аналитик арок

**Вход:**
```json
{
  "text": "текст главы/чанка",
  "current_arc_summary": "текущее summary арки",
  "task": "arc_boundary | arc_summary_start | arc_summary_update",
  "model_mode": "production | e2e-test"
}
```

**Логика:** Аналогично Summarizer — informationExtractor → Agent для Ollama.

#### 2.3.5 `[AI Agent] Analyzer` — Структурный аналитик

**Вход:**
```json
{
  "text": "полный текст файла",
  "task": "structure_analysis",
  "model_mode": "production | e2e-test"
}
```

**Логика:**
```
If model_mode == "production":
  → OpenAI model (Polza/Neuro) — informationExtractor с fallback
  
If model_mode == "e2e-test":
  → Ollama llama3.2:3b — Agent node
```

#### 2.3.6 `[AI Agent] Annotator` — Генератор аннотаций

**Вход:**
```json
{
  "book_summary": "краткое содержание книги",
  "task": "image_prompt | annotation_text",
  "model_mode": "production | e2e-test"
}
```

### 2.4 Gateway Router

**Workflow:** `[AI Gateway] Model Router`

```
Webhook / ExecuteWorkflow Trigger
         │
         ▼
┌─────────────────────────┐
│ Code: Route & Dispatch  │
│                         │
│ 1. Read agent_type      │
│ 2. Read model_mode      │
│ 3. Select sub-workflow  │
│ 4. Pass inputs          │
│ 5. Collect output       │
│ 6. Add metrics          │
│ 7. Return result        │
└─────────────────────────┘
         │
    ┌────┴────┐
    │  Switch │ (по agent_type)
    └────┬────┘
         │
    ┌────┴────────────┬────────────┬────────────┬──────────┐
    ▼                 ▼            ▼            ▼          ▼
  Translator      Posteditor   Summarizer  ArcAnalyst  Analyzer
  (executeWF)     (executeWF)  (executeWF) (executeWF) (executeWF)
```

### 2.5 Переключение режимов

#### 2.5.1 Production режим (по умолчанию)

Текущий пайплайн перевода **НЕ меняется**. Workflow `Start` → `Парсинг` → `Анализ` → `[Перевод] Перевод чанка` продолжают работать как сейчас, с Neuro/Polza.

**Gateway используется только для:**
- Новых E2E тестов
- Будущих workflow, которые будут вызывать агентов через Gateway

#### 2.5.2 E2E Test режим

Новый тестовый workflow:

```
[E2E] Translation Test
    │
    ├── 1. Подготовка тестовых данных (Тест2.docx → чанки)
    │
    ├── 2. Для каждого чанка:
    │       │
    │       ├── Вызов Gateway: agent_type=translator, model_mode=e2e-test
    │       ├── Вызов Gateway: agent_type=posteditor, model_mode=e2e-test (опционально)
    │       └── Запись результата в отдельную таблицу e2e_test_results
    │
    ├── 3. Сбор метрик:
    │       - Время на чанк
    │       - Качество (сравнение с baseline, если есть)
    │       - Ошибки / fallback count
    │       - Токены (estimated)
    │
    └── 4. Отчёт в Telegram / Dashboard
```

---

## 3. ПЛАН РЕАЛИЗАЦИИ

### Фаза 1: Подготовка (не требует изменений в production)

| # | Задача | Детали | Риск |
|---|--------|--------|------|
| 1.1 | Создать credentials для Ollama | Добавить OpenAI-compatible credential: base_url=`http://127.0.0.1:11434/v1`, model=`llama3.2:3b`, API key=`ollama` | Низкий |
| 1.2 | Создать workflow `[AI Agent] Translator` | Sub-workflow с executeWorkflowTrigger. Два набора LLM-нод: production (Neuro/Polza) и e2e (Ollama). Switch по `model_mode`. | Средний |
| 1.3 | Создать workflow `[AI Agent] Posteditor` | Аналогично Translator, но с tools. Для e2e: tools через post-processing code nodes. | Средний |
| 1.4 | Создать workflow `[AI Agent] Summarizer` | InformationExtractor для production → Agent для e2e. Адаптация промтов. | Средний |
| 1.5 | Создать workflow `[AI Agent] ArcAnalyst` | Аналогично Summarizer | Средний |
| 1.6 | Создать workflow `[AI Agent] Analyzer` | InformationExtractor → Agent для e2e | Низкий |
| 1.7 | Создать workflow `[AI Agent] Annotator` | ChainLlm → Agent для e2e | Низкий |

### Фаза 2: Gateway Router

| # | Задача | Детали | Риск |
|---|--------|--------|------|
| 2.1 | Создать `[AI Gateway] Model Router` | Webhook trigger → Code (routing) → Execute Workflow → Return | Низкий |
| 2.2 | Настроить таблицу `ai_gateway_metrics` | PostgreSQL: job_id, agent_type, model_mode, model_used, latency_ms, fallback_used, error, timestamp | Низкий |
| 2.3 | Тестирование Gateway | Unit-тест: вызвать каждый agent_type в обоих режимах | Низкий |

### Фаза 3: E2E Test Pipeline

| # | Задача | Детали | Риск |
|---|--------|--------|------|
| 3.1 | Создать `[E2E] Translation Test` | Webhook trigger → подготовка данных → цикл по чанкам → Gateway вызов → метрики | Низкий |
| 3.2 | Настроить БД для E2E | Таблица `e2e_test_results` или использование существующих таблиц с отдельным job_id | Низкий |
| 3.3 | Подготовить Тест2.docx | Загрузить файл, распарсить, создать чанки | Низкий |
| 3.4 | Запустить E2E тест | Запустить через webhook, проверить результаты | Низкий |

### Фаза 4: Миграция production (опционально, позже)

| # | Задача | Детали | Риск |
|---|--------|--------|------|
| 4.1 | Обновить `[Перевод] Перевод чанка` | Заменить встроенные LLM-ноды на вызов `[AI Agent] Translator` через Gateway | **Высокий** — требует тщательного тестирования |
| 4.2 | Обновить `Постредактура` | Заменить на `[AI Agent] Posteditor` | **Высокий** |
| 4.3 | Обновить `[Перевод] Глава` | Заменить на `[AI Agent] Summarizer` | **Высокий** |
| 4.4 | Обновить `[Перевод] Арка` | Заменить на `[AI Agent] ArcAnalyst` | **Высокий** |
| 4.5 | Обновить `Предварительный анализ` | Заменить на `[AI Agent] Analyzer` | Средний |
| 4.6 | Обновить `Анотация` | Заменить на `[AI Agent] Annotator` | Низкий |

---

## 4. КОНТРАКТЫ AGENT'ОВ

### 4.1 Стандартный вход (все агенты)

```json
{
  "agent_type": "translator | posteditor | summarizer | arcanalyst | analyzer | annotator",
  "model_mode": "production | e2e-test",
  "job_id": "string (опционально)",
  "inputs": {
    // Зависит от agent_type — см. спецификацию каждого агента
  }
}
```

### 4.2 Стандартный выход (все агенты)

```json
{
  "success": true,
  "output": "...",
  "model_used": "neuro/gpt-5.2-chat-latest",
  "fallback_used": false,
  "latency_ms": 3200,
  "tokens_estimated": 450,
  "error": null,
  "metadata": {
    "agent_type": "translator",
    "model_mode": "e2e-test",
    "job_id": "e2e-001",
    "timestamp": "2026-04-12T18:00:00Z"
  }
}
```

---

## 5. СРАВНЕНИЕ PATTERNS: Production vs E2E

| Аспект | Production (платные) | E2E (Ollama) |
|--------|---------------------|--------------|
| **Модель** | GPT-5.2, GPT-5.3, Claude 4.5, Gemini | llama3.2:3b |
| **Provider** | Neuro API, Polza API | Ollama (localhost) |
| **Credential** | Neuroapi, Polza | Ollama (OpenAI-compatible) |
| **Agent node** | `@n8n/n8n-nodes-langchain.agent` | `@n8n/n8n-nodes-langchain.agent` |
| **Fallback** | Neuro → Polza (разные API) | Ollama retry |
| **InformationExtractor** | ✅ Поддерживается | ❌ Не поддерживается → используем Agent |
| **AI Tools (function calling)** | ✅ Нативная поддержка | ❌ Не поддерживается → post-processing |
| **Температура/параметры** | Настраиваются per-provider | Настраиваются для Ollama |
| **Стоимость** | Платно | Бесплатно |
| **Скорость** | ~1-3 сек/чанк | ~5-15 сек/чанк (зависит от GPU/CPU) |

---

## 6. ГАРАНТИИ ПРОИЗВОДИТЕЛЬНОСТИ

### 6.1 Production НЕ затрагивается

- Текущие workflow (`[Перевод] Перевод чанка`, `Постредактура`, и т.д.) **остаются без изменений** до Фазы 4
- Gateway — **новая точка входа**, не замена существующим workflow
- Production и E2E используют **разные job_id** → данные не пересекаются
- Модели Ollama работают локально → **нет нагрузки на production API**

### 6.2 E2E изоляция

- E2E тесты пишут в отдельную таблицу `e2e_test_results`
- E2E job_id имеют префикс `e2e-` → легко отличить от production
- При необходимости: E2E можно запустить на отдельной копии БД

### 6.3 Rollback

- Если Gateway окажется проблематичным: просто не использовать его
- Production workflow продолжают работать как раньше
- Никаких breaking changes до Фазы 4

---

## 7. НЕОБХОДИМЫЕ РЕСУРСЫ

### 7.1 Модели Ollama

Требуется установить для E2E тестирования:

```bash
# Текущая модель (уже есть)
ollama pull llama3.2:3b

# Рекомендуемые дополнительные модели:
ollama pull llama3.1:8b        # Более качественный перевод
ollama pull qwen2.5:7b         # Хорош для корейского → русского
ollama pull nomic-embed-text   # Уже есть, для embeddings
```

### 7.2 Database

Новые таблицы:

```sql
-- Метрики AI Gateway
CREATE TABLE ai_gateway_metrics (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(100),
    agent_type VARCHAR(50),
    model_mode VARCHAR(20),
    model_used VARCHAR(100),
    latency_ms INTEGER,
    fallback_used BOOLEAN,
    tokens_estimated INTEGER,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Результаты E2E тестов
CREATE TABLE e2e_test_results (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(100),
    chunk_id INTEGER,
    ko_text TEXT,
    ai_output TEXT,
    agent_type VARCHAR(50),
    model_used VARCHAR(100),
    latency_ms INTEGER,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Сравнение с baseline (для оценки качества)
CREATE TABLE e2e_quality_comparison (
    id SERIAL PRIMARY KEY,
    e2e_job_id VARCHAR(100),
    baseline_job_id VARCHAR(100),
    chunk_id INTEGER,
    e2e_output TEXT,
    baseline_output TEXT,
    similarity_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.3 n8n Credentials

Новые credential:
- **Ollama (OpenAI-compatible):**
  - Type: OpenAI API
  - Base URL: `http://127.0.0.1:11434/v1`
  - API Key: `ollama` (любое значение)
  - Model: `llama3.2:3b`

---

## 8. ПОРЯДОК ВЫПОЛНЕНИЯ

1. **Фаза 1** (подготовка) — создаём 6 agent-воркфлоу + Ollama credential
2. **Фаза 2** (Gateway) — создаём роутер + таблицу метрик
3. **Фаза 3** (E2E) — запускаем тестовый пайплайн на Тест2.docx
4. **Фаза 4** (миграция) — **только после одобрения**, постепенно заменяем production workflow

---

## 9. РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Ollama llama3.2:3b недостаточно качествен для перевода | Высокая | Качество E2E | Использовать более крупные модели (qwen2.5:14b, llama3.1:8b) |
| Ollama не поддерживает InformationExtractor | — | Структурные изменения | Используем Agent node с адаптированным промтом |
| Ollama не поддерживает function calling | — | Постредактор без tools | Post-processing code nodes |
| Конфликт production/E2E данных | Низкая | Корректность метрик | Раздельные job_id, таблицы |
| Деградация production при Фазе 4 | Средняя | Перевод книг | Поэтапная миграция, откат через version rollback |
| Нехватка ресурсов для Ollama | Средняя | Скорость E2E | Мониторинг CPU/RAM, настройка контекста |

---

## 10. РЕШЕНИЯ

### Почему не замена, а шлюз?

Потому что production-перевод должен работать **бесперебойно**. Gateway — это надстройка, которая:
- Не трогает работающие workflow
- Позволяет тестировать новые модели параллельно
- Даёт единый интерфейс для будущего рефакторинга

### Почему 6 отдельных агентов, а не один?

Потому что каждый агент имеет **уникальный паттерн**:
- Переводчик: Agent с fallback
- Постредактор: Agent с tools
- Саммаризатор: InformationExtractor
- Арка-аналитик: InformationExtractor (другие промты)
- Структурный аналитик: InformationExtractor с fallback
- Аннотатор: ChainLlm

Объединение в один workflow создало бы монстр на 100+ узлов, который невозможно поддерживать.

### Почему `model_mode` в каждом вызове, а не глобальная настройка?

Потому что мы хотим:
- Запускать E2E тесты **параллельно** с production
- Возможность A/B тестирования (один чанк на production, один на e2e)
- Гибкость: разные агенты могут использовать разные режимы

---

## 11. ФАЗА 1 — РЕЗУЛЬТАТ (2026-04-12)

### Созданные ресурсы

**Credential:**
| Name | ID | Type | Base URL |
|------|-----|------|----------|
| Ollama | `JD2Nq8h0kULY7Ly3` | openAiApi | http://127.0.0.1:11434/v1 |

**Agent-Workflow (все inactive, все валидны):**
| # | Имя | ID | Узлы | Pattern |
|---|-----|----|-----|---------|
| 1 | `[AI Agent] Translator` | `x9YebMmxj7jWMaYL` | 9 | Agent w/fallback (production→e2e) |
| 2 | `[AI Agent] Posteditor` | `qLWDoX8gMxxwdGNL` | 11 | Agent w/fallback + post-processing tools |
| 3 | `[AI Agent] Summarizer` | `DW87nltHKe2kPtbl` | 8 | InfoExtractor → Agent |
| 4 | `[AI Agent] ArcAnalyst` | `1Y5xWSvnFzWhOPqm` | 8 | InfoExtractor → Agent |
| 5 | `[AI Agent] Analyzer` | `M9yFn9uyrGEBn4tB` | 8 | InfoExtractor → Agent |
| 6 | `[AI Agent] Annotator` | `3Jats5dAH02lPZ9R` | 8 | Agent → Agent |

**Архитектура каждого workflow:**
```
Start (executeWorkflowTrigger) → Switch (по model_mode)
  → production: LLM-ноды (Neuro/Polza/OpenAI credential)
  → e2e-test:   Ollama llama3.2:3b (credential: JD2Nq8h0kULY7Ly3)
  → Merge Results (chooseBranch) → Format Output (standardized JSON)
```

**План отката:**
- Каждый workflow можно удалить: `n8n_delete_workflow` по ID
- Credential можно удалить: `n8n_manage_credentials(action=delete, id=JD2Nq8h0kULY7Ly3)`
- Production workflow НЕ модифицированы
- Все новые workflow inactive (не запускаются)

**Статус:** ✅ Фаза 1 завершена

---

*Документ создан: 2026-04-12*  
*Фаза 1 завершена: 2026-04-12*  
*Следующий шаг: Фаза 2 — AI Gateway Model Router*
