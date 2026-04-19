# 🔥 Firecrawl Self-Hosted — Полная документация

**Дата:** 11 апреля 2026 г.
**Версия:** 1.0
**Хост:** Linux (32GB RAM, 131GB свободно)
**Порт:** 3002
**URL:** `http://localhost:3002`

---

## Содержание

1. [Что такое Firecrawl](#что-такое-firecrawl)
2. [Архитектура](#архитектура)
3. [Установка](#установка)
4. [Конфигурация](#конфигурация)
5. [Запуск](#запуск)
6. [API Reference](#api-reference)
7. [Интеграция с MCP](#интеграция-с-mcp)
8. [Интеграция с n8n](#интеграция-с-n8n)
9. [Мониторинг](#мониторинг)
10. [Troubleshooting](#troubleshooting)
11. [Безопасность](#безопасность)

---

## Что такое Firecrawl

**Firecrawl** — open-source API для скрапинга и краулинга веб-сайтов. Превращает сайты в LLM-ready данные (markdown, JSON).

### Возможности

| Функция | Описание |
|---------|----------|
| **Scrape** | Скрейпинг одной страницы → markdown |
| **Crawl** | Краулинг всего сайта → множество страниц |
| **Extract** | Извлечение структурированных данных (AI) |
| **Search** | Поиск по веб-страницам |
| **Map** | Карта всех URL сайта |
| **Batch** | Пакетная обработка URL |

### Зачем self-hosted?

- ✅ **Без лимитов** — нет ограничений по кредитам
- ✅ **Приватность** — данные не покидают ваш сервер
- ✅ **Бесплатно** — не нужна подписка
- ✅ **Контроль** — полный контроль над конфигурацией
- ⚠️ **Требует ресурсов** — ~12GB RAM, ~5GB disk

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    Firecrawl Stack                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────┐    ┌──────────────────────────────┐   │
│  │    API       │───▶│   Playwright Service          │   │
│  │  (port 3002) │    │   (headless browser, port 3K)│   │
│  └──────┬───────┘    └──────────────────────────────┘   │
│         │                                                 │
│         ├──▶ Redis (queues, rate limiting, port 6379)    │
│         │                                                 │
│         ├──▶ RabbitMQ (job broker, port 5672)            │
│         │                                                 │
│         └──▶ PostgreSQL (data storage, port 5432)        │
│                                                          │
│  External Access: http://localhost:3002                  │
│  Admin Panel: http://localhost:3002/admin/{KEY}/queues   │
└─────────────────────────────────────────────────────────┘
```

### Сервисы и ресурсы

| Сервис | RAM | CPU | Описание |
|--------|-----|-----|----------|
| **api** | 8GB | 4.0 | Основной API сервер |
| **playwright-service** | 4GB | 2.0 | Headless Chrome для рендеринга |
| **redis** | 512MB | 0.5 | Очереди, кэш, rate limiting |
| **rabbitmq** | 512MB | 0.5 | Брокер задач |
| **nuq-postgres** | 1GB | 1.0 | База данных |
| **ИТОГО** | **~14GB** | **~8.0** | |

> ⚠️ **У вас 32GB RAM, из них 17GB свободно.** Firecrawl займёт ~14GB. Учитывайте что у вас уже работают n8n, PostgreSQL, Grafana, Ollama.

### Рекомендуемые настройки для вашего сервера

Уменьшим ресурсы для firecrawl чтобы ужиться с другими сервисами:

```yaml
# Рекомендуемые лимиты для вашего сервера
api:              4GB RAM, 2 CPU  (вместо 8GB/4CPU)
playwright:       2GB RAM, 1 CPU  (вместо 4GB/2CPU)
redis:            256MB RAM       (вместо 512MB)
rabbitmq:         256MB RAM       (вместо 512MB)
nuq-postgres:     512MB RAM       (вместо 1GB)
ИТОГО:            ~7GB RAM, ~3CPU
```

---

## Установка

### Шаг 1: Клонирование репозитория

```bash
cd /home/user
git clone https://github.com/firecrawl/firecrawl.git
cd firecrawl
```

### Шаг 2: Создание .env файла

```bash
cat > .env << 'ENVEOF'
# ===== ОБЯЗАТЕЛЬНЫЕ =====
PORT=3002
HOST=0.0.0.0
INTERNAL_PORT=3002

# ===== Аутентификация =====
# Для self-hosted без DB auth
USE_DB_AUTHENTICATION=false

# Ключ для админ-панели очередей (ЗАМЕНИТЕ на свой!)
BULL_AUTH_KEY=firecrawl-admin-secret-key-2026

# ===== AI функции (опционально) =====
# Вариант 1: OpenAI (для extract/structured data)
# OPENAI_API_KEY=sk-your-openai-key

# Вариант 2: Ollama (ЛОКАЛЬНЫЙ, уже работает на порту 11434!)
OLLAMA_BASE_URL=http://host.docker.internal:11434/api
MODEL_NAME=qwen2.5:32b
MODEL_EMBEDDING_NAME=qwen2.5:32b

# Вариант 3: Любая OpenAI-совместимая API
# OPENAI_BASE_URL=http://host.docker.internal:11434/v1
# OPENAI_API_KEY=ollama

# ===== Прокси (опционально) =====
# Используйте ваш Xray/Hiddify прокси
# PROXY_SERVER=http://127.0.0.1:10808
# PROXY_USERNAME=
# PROXY_PASSWORD=

# ===== Поиск (опционально) =====
# SEARXNG_ENDPOINT=http://your.searxng.server

# ===== Логирование =====
LOGGING_LEVEL=info

# ===== Webhook для уведомлений (опционально) =====
# SELF_HOSTED_WEBHOOK_URL=http://localhost:5678/webhook/firecrawl

# ===== Настройки производительности =====
# УМЕНЬШЕНО для вашего сервера (32GB, много других сервисов)
NUM_WORKERS_PER_QUEUE=4
CRAWL_CONCURRENT_REQUESTS=5
MAX_CONCURRENT_JOBS=3
BROWSER_POOL_SIZE=3

# ===== PostgreSQL =====
POSTGRES_USER=firecrawl
POSTGRES_PASSWORD=firecrawl_secure_password_2026
POSTGRES_DB=firecrawl
POSTGRES_HOST=nuq-postgres
POSTGRES_PORT=5432

# ===== Redis =====
REDIS_URL=redis://redis:6379
REDIS_RATE_LIMIT_URL=redis://redis:6379
ENVEOF

echo "✅ .env файл создан"
cat .env | grep -v "^$" | grep -v "^#" | wc -l
echo "строк конфигурации"
```

### Шаг 3: Оптимизация docker-compose.yaml для вашего сервера

Создадим оптимизированную версию:

```bash
# Скачаем оригинальный docker-compose.yaml
curl -sL https://raw.githubusercontent.com/mendableai/firecrawl/main/docker-compose.yaml -o docker-compose.yaml

echo "✅ docker-compose.yaml скачан"
```

### Шаг 4: Сборка и запуск

```bash
# Первый запуск (займёт 10-20 минут — скачивание образов и сборка)
cd /home/user/firecrawl
docker compose build
docker compose up -d

# Проверка статуса
docker compose ps

# Проверка логов
docker compose logs -f api
```

### Шаг 5: Тестирование

```bash
# Тест scrape (одна страница)
curl -s -X POST http://localhost:3002/v1/scrape \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}' | python3 -m json.tool | head -30

# Тест crawl (весь сайт)
curl -s -X POST http://localhost:3002/v1/crawl \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://example.com",
    "limit": 5
  }' | python3 -m json.tool

# Тест map (карта URL)
curl -s -X POST http://localhost:3002/v1/map \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}' | python3 -m json.tool
```

---

## Конфигурация

### Все доступные Environment Variables

#### Обязательные

| Переменная | Значение | Описание |
|-----------|----------|----------|
| `PORT` | 3002 | Порт API (внешний) |
| `HOST` | 0.0.0.0 | Bind адрес |
| `INTERNAL_PORT` | 3002 | Внутренний порт API |
| `USE_DB_AUTHENTICATION` | false | Отключить auth (для self-hosted) |
| `BULL_AUTH_KEY` | ваш-ключ | Пароль для админ-панели |

#### AI функции

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `OPENAI_API_KEY` | OpenAI API ключ | `sk-proj-...` |
| `OPENAI_BASE_URL` | Кастомная OpenAI API | `http://host.docker.internal:11434/v1` |
| `MODEL_NAME` | Модель для извлечения данных | `qwen2.5:32b` |
| `MODEL_EMBEDDING_NAME` | Модель для эмбеддингов | `nomic-embed-text` |
| `OLLAMA_BASE_URL` | Ollama API URL | `http://host.docker.internal:11434/api` |

#### Производительность

| Переменная | По умолчанию | Рекомендация (32GB) | Описание |
|-----------|-------------|---------------------|----------|
| `NUM_WORKERS_PER_QUEUE` | 8 | 4 | Кол-во воркеров в очереди |
| `CRAWL_CONCURRENT_REQUESTS` | 10 | 5 | Параллельные запросы при краулинге |
| `MAX_CONCURRENT_JOBS` | 5 | 3 | Макс. одновременных задач |
| `BROWSER_POOL_SIZE` | 5 | 3 | Пул headless браузеров |

#### Прокси

| Переменная | Описание |
|-----------|----------|
| `PROXY_SERVER` | URL прокси сервера |
| `PROXY_USERNAME` | Имя пользователя прокси |
| `PROXY_PASSWORD` | Пароль прокси |

#### PostgreSQL

| Переменная | Значение | Описание |
|-----------|----------|----------|
| `POSTGRES_USER` | firecrawl | Пользователь БД |
| `POSTGRES_PASSWORD` | ваш-пароль | Пароль БД |
| `POSTGRES_DB` | firecrawl | Имя БД |

#### Redis

| Переменная | Значение | Описание |
|-----------|----------|----------|
| `REDIS_URL` | redis://redis:6379 | URL Redis для очередей |
| `REDIS_RATE_LIMIT_URL` | redis://redis:6379 | URL Redis для rate limiting |

---

## Запуск

### Основные команды

```bash
cd /home/user/firecrawl

# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Логи (все сервисы)
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f api
docker compose logs -f playwright-service
docker compose logs -f redis
docker compose logs -f rabbitmq
docker compose logs -f nuq-postgres

# Статус
docker compose ps

# Пересборка (после изменения кода)
docker compose build
docker compose up -d

# Очистка (удалит все данные!)
docker compose down -v
```

### Systemd сервис (автозапуск)

```bash
sudo tee /etc/systemd/system/firecrawl.service << 'EOF'
[Unit]
Description=Firecrawl Self-Hosted
Requires=docker.service
After=docker.service
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/user/firecrawl
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable firecrawl
sudo systemctl start firecrawl

# Проверка
sudo systemctl status firecrawl
```

### Доступ через Caddy (домен)

```bash
# Добавьте в Caddyfile (n8n-docker/Caddyfile):
firecrawl.bigalexn8n.ru {
    reverse_proxy localhost:3002
}

# Перезапуск Caddy
docker restart n8n-docker-caddy-1
```

Теперь доступ: `https://firecrawl.bigalexn8n.ru`

---

## API Reference

### 1. Scrape — Скрейпинг одной страницы

```bash
POST /v1/scrape
```

**Request:**
```json
{
  "url": "https://example.com",
  "formats": ["markdown", "html"],
  "onlyMainContent": true,
  "waitFor": 1000,
  "timeout": 30000,
  "mobile": false,
  "skipTlsVerification": false,
  "removeBase64Images": true,
  "extract": {
    "schema": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "author": {"type": "string"}
      }
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "markdown": "# Example Domain\n\nThis domain is for use in...",
    "html": "<html>...</html>",
    "metadata": {
      "title": "Example Domain",
      "url": "https://example.com",
      "statusCode": 200
    }
  }
}
```

### 2. Crawl — Краулинг всего сайта

```bash
POST /v1/crawl
```

**Request:**
```json
{
  "url": "https://example.com",
  "limit": 100,
  "maxDiscoveryDepth": 50,
  "allowBackwardLinks": false,
  "allowExternalLinks": false,
  "excludePaths": ["blog/*", "assets/*"],
  "includePaths": ["docs/*"],
  "ignoreSitemap": false,
  "scrapeOptions": {
    "formats": ["markdown"],
    "onlyMainContent": true
  },
  "webhook": {
    "url": "http://localhost:5678/webhook/firecrawl",
    "headers": {"Authorization": "Bearer your-key"}
  }
}
```

**Response:**
```json
{
  "success": true,
  "id": "crawl-abc123-def456",
  "url": "https://example.com"
}
```

**Получение результатов:**
```bash
GET /v1/crawl/{crawl_id}
```

### 3. Map — Карта URL сайта

```bash
POST /v1/map
```

**Request:**
```json
{
  "url": "https://example.com",
  "search": "docs",
  "ignoreSitemap": false,
  "sitemapOnly": false,
  "includeSubdomains": false
}
```

### 4. Extract — Извлечение структурированных данных (AI)

```bash
POST /v1/extract
```

**Request:**
```json
{
  "urls": ["https://example.com/page1", "https://example.com/page2"],
  "prompt": "Extract all product names and prices",
  "schema": {
    "type": "object",
    "properties": {
      "products": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "price": {"type": "number"}
          }
        }
      }
    }
  }
}
```

### 5. Search — Поиск

```bash
POST /v1/search
```

**Request:**
```json
{
  "query": "firecrawl documentation",
  "limit": 10,
  "tbs": "qdr:m",
  "lang": "ru",
  "country": "ru"
}
```

---

## Интеграция с MCP

### Обновление конфигурации

Файл: `~/.qwen/settings.json`

```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": [
        "-y",
        "firecrawl-mcp"
      ],
      "env": {
        "FIRECRAWL_API_URL": "http://localhost:3002"
      }
    }
  }
}
```

**Обратите внимание:** `FIRECRAWL_API_KEY` НЕ нужен для self-hosted без auth.

### Перезапуск Qwen Code

После изменения settings.json — перезапустите Qwen Code.

### Проверка работы

```bash
# Проверка MCP сервера
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | FIRECRAWL_API_URL=http://localhost:3002 npx -y firecrawl-mcp 2>/dev/null | tail -1 | python3 -m json.tool
```

---

## Интеграция с n8n

### Вариант 1: HTTP Request Node

```
[Manual Trigger] → [HTTP Request] → [JSON Parse] → [Output]
```

**HTTP Request Node Config:**
```
Method: POST
URL: http://localhost:3002/v1/scrape
Authentication: None
Headers:
  Content-Type: application/json
Body:
{
  "url": "{{ $json.url }}",
  "formats": ["markdown"],
  "onlyMainContent": true
}
```

### Вариант 2: Webhook для асинхронного crawl

```
[Webhook] → [HTTP Request: Get Crawl Status] → [Loop until complete] → [Process Results]
```

### Вариант 3: n8n Community Node

Установите `n8n-nodes-firecrawl` если доступен:

```bash
cd /home/user/n8n-docker
# Проверьте доступные community nodes
```

---

## Мониторинг

### Админ-панель очередей

```
http://localhost:3002/admin/{BULL_AUTH_KEY}/queues
```

Замените `{BULL_AUTH_KEY}` на значение из `.env` (по умолчанию: `firecrawl-admin-secret-key-2026`)

### Docker логи

```bash
# Все логи
docker compose logs -f

# Только ошибки
docker compose logs -f 2>&1 | grep -i error

# API логи
docker compose logs -f api

# Playwright логи
docker compose logs -f playwright-service
```

### Prometheus + Grafana

Добавьте firecrawl в Prometheus scraping:

```yaml
# prometheus/prometheus.yml
scrape_configs:
  - job_name: 'firecrawl'
    static_configs:
      - targets: ['host.docker.internal:3002']
```

### Health Check

```bash
# Проверка работоспособности
curl -s http://localhost:3002/v1/test/token | python3 -m json.tool

# Или простой запрос
curl -s http://localhost:3002/ | python3 -m json.tool
```

### Ресурсы (docker stats)

```bash
# Мониторинг ресурсов в реальном времени
docker stats firecrawl-api firecrawl-playwright-service-1 firecrawl-redis-1 firecrawl-rabbitmq-1 firecrawl-nuq-postgres-1

# Один снимок
docker stats --no-stream
```

---

## Troubleshooting

### Проблема: Контейнер не запускается

```bash
# Проверка логов
docker compose logs api

# Проверка .env
cat .env | grep -v "^$" | grep -v "^#"

# Проверка портов
sudo ss -tlnp | grep 3002

# Пересборка
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Проблема: Out of Memory

```bash
# Проверка памяти
free -h
docker stats --no-stream

# Уменьшите воркеры в .env:
NUM_WORKERS_PER_QUEUE=2
CRAWL_CONCURRENT_REQUESTS=3
MAX_CONCURRENT_JOBS=2
BROWSER_POOL_SIZE=2

# Перезапуск
docker compose restart
```

### Проблема: Playwright не может открыть страницу

```bash
# Проверка playwright сервиса
docker compose logs playwright-service

# Проверка что браузер скачался
docker exec firecrawl-playwright-service-1 npx playwright install --dry-run

# Переустановка браузеров
docker compose down
docker compose build --no-cache playwright-service
docker compose up -d
```

### Проблема: Redis/RabbitMQ не запускаются

```bash
# Проверка Redis
docker compose logs redis
docker exec firecrawl-redis-1 redis-cli ping  # Должен ответить PONG

# Проверка RabbitMQ
docker compose logs rabbitmq
docker exec firecrawl-rabbitmq-1 rabbitmq-diagnostics check_running
```

### Проблема: Медленный краулинг

```bash
# Увеличьте воркеры (если есть ресурсы)
# В .env:
NUM_WORKERS_PER_QUEUE=8
CRAWL_CONCURRENT_REQUESTS=10
MAX_CONCURRENT_JOBS=5
BROWSER_POOL_SIZE=5

# Перезапуск
docker compose restart

# Мониторинг
docker compose logs -f api | grep -i "crawl\|scrape"
```

### Проблема: Конфликт портов

```bash
# Проверка что использует порт 3002
sudo ss -tlnp | grep 3002

# Измените порт в .env:
PORT=3003
INTERNAL_PORT=3003

# Перезапуск
docker compose down
docker compose up -d
```

### Полный сброс

```bash
cd /home/user/firecrawl

# Остановка + удаление volumes (ВСЕ ДАННЫЕ БУДУТ УДАЛЕНЫ!)
docker compose down -v

# Удаление образов
docker compose rm -f

# Чистая пересборка
docker compose build --no-cache
docker compose up -d
```

---

## Безопасность

### 🔴 Критично

1. **Смените BULL_AUTH_KEY** — используйте уникальный ключ!
   ```bash
   # Сгенерируйте случайный ключ
   openssl rand -hex 32
   ```

2. **PostgreSQL пароль** — используйте сложный пароль
   ```bash
   openssl rand -base64 32
   ```

3. **Не открывайте порт 3002 в интернет** без auth
   - Используйте Caddy с BasicAuth
   - Или настройте `USE_DB_AUTHENTICATION=true` + Supabase

### 🟡 Рекомендовано

4. **Rate Limiting** через Caddy:
   ```caddyfile
   firecrawl.bigalexn8n.ru {
       @crawl path /v1/crawl*
       rate_limit @crawl 10r/m

       reverse_proxy localhost:3002
   }
   ```

5. **Используйте прокси** для анонимности:
   ```env
   PROXY_SERVER=http://127.0.0.1:10808
   ```

6. **Ограничьте доступ к админ-панели**:
   ```bash
   # Доступ только с localhost
   # Не открывайте /admin/* в Caddy
   ```

7. **Регулярно обновляйте**:
   ```bash
   cd /home/user/firecrawl
   git pull
   docker compose build
   docker compose up -d
   ```

8. **Бэкап данных**:
   ```bash
   # PostgreSQL бэкап
   docker exec firecrawl-nuq-postgres-1 pg_dump -U firecrawl firecrawl > firecrawl_db_$(date +%F).sql

   # Восстановление
   cat firecrawl_db_2026-04-11.sql | docker exec -i firecrawl-nuq-postgres-1 psql -U firecrawl firecrawl
   ```

---

## Быстрый старт (copy-paste)

```bash
# Всё в одном
cd /home/user
git clone https://github.com/firecrawl/firecrawl.git
cd firecrawl

# .env
cat > .env << 'EOF'
PORT=3002
HOST=0.0.0.0
INTERNAL_PORT=3002
USE_DB_AUTHENTICATION=false
BULL_AUTH_KEY=$(openssl rand -hex 16)
OLLAMA_BASE_URL=http://host.docker.internal:11434/api
MODEL_NAME=qwen2.5:32b
NUM_WORKERS_PER_QUEUE=4
CRAWL_CONCURRENT_REQUESTS=5
MAX_CONCURRENT_JOBS=3
BROWSER_POOL_SIZE=3
POSTGRES_USER=firecrawl
POSTGRES_PASSWORD=$(openssl rand -base64 24)
POSTGRES_DB=firecrawl
LOGGING_LEVEL=info
EOF

# Запуск
docker compose up -d

# Проверка
sleep 30
curl -s -X POST http://localhost:3002/v1/scrape \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}' | python3 -m json.tool | head -20

# Показать URL админки
echo "Admin Panel: http://localhost:3002/admin/$(grep BULL_AUTH_KEY .env | cut -d= -f2)/queues"
```

---

*Документация актуальна на 11 апреля 2026 г. Версия Firecrawl: latest (main branch)*
