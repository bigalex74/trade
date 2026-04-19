# Документация воркфлоу "Send Message"

## 📋 Обзор

Система уведомлений в Telegram для отслеживания процесса перевода документов.

### Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│  main_send_message (Orchestrator + Business Logic)             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ БИЗНЕС-ЛОГИКА:                                           │  │
│  │ - DB Trigger на telegram_send_message                    │  │
│  │ - Валидация payload                                      │  │
│  │ - Идемпотентность                                        │  │
│  │ - Координация подворкфлоу                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │
         ├──► sub_get_context ────────┐ (данные о задаче)
         │                            │
         ├──► task_create ────────────┤
         ├──► task_start_processing ──┤
         ├──► task_process ───────────┤
         ├──► task_error ─────────────┤
         ├──► task_finish ────────────┤
         ├──► task_stop ──────────────┤
         │                            ↓
         └──► sub_notify_telegram ◄─── (message + type + button)
                   │
                   └──► Log To DB (логирование отправки)
```

---

## 🗂️ Компоненты

### 1. main_send_message (Оркестратор)

**ID:** `main_send_message`  
**Описание:** Главный воркфлоу, координирующий все процессы

**Узлы:**
| Узел | Тип | Описание |
|------|-----|----------|
| DB Trigger | PostgresTrigger | Слушает INSERT на `telegram_send_message` |
| Validate Payload | Code | Валидация и идемпотентность |
| Get Context | Execute Workflow | Получение данных о задаче |
| Router | Switch | Роутинг по 6 типам сообщений |
| Task * | Execute Workflow | Вызов task_* воркфлоу |
| Notify Telegram | Execute Workflow | Отправка в Telegram |
| Log Result | Code | Финальное логирование |

---

### 2. sub_get_context (Context Provider)

**ID:** `sub_get_context`  
**Описание:** Получение полного контекста задачи

**Input:**
```json
{
  "job_id": "number (опционально, берётся из job_current)"
}
```

**Output:**
```json
{
  "job_id": "number",
  "file_name": "string",
  "translated_file": "string",
  "billing_polza": "number",
  "billing_neuro": "number",
  "amount": "number",
  "total_usage": "number",
  "created_at": "ISO date",
  "finished_at": "ISO date (nullable)",
  "error_text": "string (nullable)",
  "chunks_total": "number",
  "chunks_done": "number",
  "message_id": "number (nullable, для идемпотентности)"
}
```

**SQL запрос:**
```sql
SELECT 
  j.job_id,
  j.file_name,
  j.translated_file,
  j.billing_polza,
  j.billing_neuro,
  j.amount,
  j.total_usage,
  j.created_at,
  j.finished_at,
  j.error_text,
  (SELECT COUNT(*) FROM document_chunks WHERE job_id = j.job_id) as chunks_total,
  (SELECT COUNT(*) FROM document_chunks WHERE job_id = j.job_id AND status = 'done') as chunks_done,
  (SELECT message_id FROM telegram_send_message 
   WHERE job_id = j.job_id AND type IN ('start', 'process') 
   ORDER BY id DESC LIMIT 1) as message_id
FROM document_jobs j
JOIN job_current jc ON j.id = jc.job_id
WHERE j.job_id = (SELECT job_id FROM job_current LIMIT 1)
LIMIT 1;
```

---

### 3. task_* (Message Formatters)

**6 независимых воркфлоу для форматирования сообщений**

#### task_create
**ID:** `task_create`  
**Сообщение:** "🆕 Задача создана"  
**Кнопки:** Нет

#### task_start_processing
**ID:** `task_start_processing`  
**Сообщение:** "▶️ Обработка началась"  
**Кнопки:** Нет

#### task_process
**ID:** `task_process`  
**Сообщение:** "🔄 Перевод в процессе" с прогресс-баром  
**Кнопки:** Нет

#### task_error
**ID:** `task_error`  
**Сообщение:** "⚠️ Ошибка обработки"  
**Кнопки:** Нет

#### task_finish
**ID:** `task_finish`  
**Сообщение:** "✅ Перевод завершен!" с итогами  
**Кнопки:** Нет

#### task_stop
**ID:** `task_stop`  
**Сообщение:** "🚨 Перевод остановлен"  
**Кнопки:** ✅ "🔁 Повторить" (callback: `repeat_translate`)

**Общий контракт task_*:**

**Input:**
```json
{
  "file_name": "string (required)",
  "translated_file": "string (optional)",
  "billing_polza": "number (optional)",
  "billing_neuro": "number (optional)",
  "chunks_total": "number (optional)",
  "chunks_done": "number (optional)",
  "error_text": "string (optional, только для task_error)"
}
```

**Output:**
```json
{
  "message": "string (HTML, required)",
  "type": "string (create|start|process|error|finish|stop)",
  "button": "object (optional)"
}
```

---

### 4. sub_notify_telegram (Notification Service)

**ID:** `sub_notify`  
**Описание:** Отправка/редактирование сообщений в Telegram

**Input:**
```json
{
  "message": "string (HTML)",
  "type": "string (create|edit)",
  "button": "object (optional)",
  "message_id": "number (optional, для редактирования)"
}
```

**Логика идемпотентности:**
1. Если `type='edit'` И `message_id` существует → **Edit Message**
2. Иначе → **Send Message**

**Обработка ошибок:**
- Rate limit → продолжение без прерывания
- Message not modified → игнорирование
- Другие ошибки → логирование в БД

**Логирование:**
```sql
INSERT INTO telegram_send_message (chat_id, message, message_id, type, status, created_at)
VALUES (...)
ON CONFLICT (chat_id, type) 
DO UPDATE SET 
  message_id = EXCLUDED.message_id,
  status = EXCLUDED.status,
  updated_at = NOW();
```

---

## 🔄 Типы сообщений

| payload.message | notify_type | task_* | type для Telegram |
|-----------------|-------------|--------|-------------------|
| `create_job` | create | task_create | create |
| `start_processing` | start | task_start_processing | start |
| `processing` | process | task_process | process |
| `error_processing` | error | task_error | error |
| `finish_processing` | finish | task_finish | finish |
| `stop_processing` | stop | task_stop | stop |

---

## 🧪 Тестирование

### Юнит-тесты (через Pin Data)

**UT-01: task_create**
```json
{
  "file_name": "Test.pdf"
}
```
**Ожидаемо:** Сообщение "🆕 Задача создана"

**UT-02: task_process**
```json
{
  "file_name": "Test.pdf",
  "chunks_done": 5,
  "chunks_total": 10,
  "billing_polza": 100,
  "billing_neuro": 50,
  "created_at": "2026-03-28T10:00:00Z"
}
```
**Ожидаемо:** Прогресс-бар 50%

### Интеграционные тесты (SQL)

**Запуск:**
```bash
docker exec n8n-docker-db-1 psql -U n8n_user -d n8n_database -f /home/user/test_send_message.sql
```

**Тесты:**
1. **IT-01:** Создание задачи → сообщение "🆕"
2. **IT-02:** Начало обработки → сообщение "▶️"
3. **IT-03:** Прогресс 50% → сообщение "🔄" с прогресс-баром
4. **IT-04:** Ошибка → сообщение "⚠️"
5. **IT-05:** Завершение → сообщение "✅"
6. **IT-06:** Остановка → сообщение "🚨" + кнопка
7. **IT-07:** Идемпотентность → редактирование вместо создания

---

## 🔧 Настройка

### Переменные окружения

Добавить в `/home/user/n8n-docker/.env`:

```bash
# Exchange rate для конвертации
N8N_RUBLE_EXCHANGE_RATE=79

# Retry настройки
N8N_DEFAULT_RETRY_COUNT=3
N8N_DEFAULT_RETRY_DELAY=5000
```

### Триггер в БД

Автоматическое создание записей для логирования:

```sql
-- Проверка существования триггера
SELECT * FROM information_schema.triggers 
WHERE trigger_name = 'tg_send_message_notify';

-- Создание при необходимости
CREATE OR REPLACE FUNCTION notify_telegram_message()
RETURNS TRIGGER AS $$
BEGIN
  -- Триггер активирует main_send_message через n8n PostgresTrigger
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_send_message_notify
AFTER INSERT ON telegram_send_message
FOR EACH ROW
EXECUTE FUNCTION notify_telegram_message();
```

---

## 📊 Мониторинг

### Статус сообщений

```sql
SELECT 
  type,
  status,
  COUNT(*) as count,
  MAX(updated_at) as last_updated
FROM telegram_send_message
GROUP BY type, status
ORDER BY type, status;
```

### Ошибки отправки

```sql
SELECT *
FROM telegram_send_message
WHERE status = 'error'
ORDER BY created_at DESC
LIMIT 10;
```

### Задержки отправки

```sql
SELECT 
  type,
  AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_delay_sec
FROM telegram_send_message
WHERE status = 'sent'
GROUP BY type;
```

---

## 🐛 Troubleshooting

### Сообщение не отправляется

1. Проверить статус воркфлоу:
   ```sql
   SELECT name, active, "updatedAt" 
   FROM workflow_entity 
   WHERE name LIKE '%Send Message%';
   ```

2. Проверить логи n8n:
   ```bash
   docker logs n8n-docker-n8n-1 --tail 100
   ```

3. Проверить Telegram API:
   ```bash
   curl "https://api.telegram.org/bot8591497428:AAEbVnPaXYe2E-WI2ni2cCuSGnS5sckR0/getMe"
   ```

### Дублирование сообщений

Проверить идемпотентность:
```sql
SELECT 
  job_id,
  type,
  message_id,
  status,
  created_at,
  updated_at
FROM telegram_send_message
WHERE job_id = 9001
ORDER BY id;
```

### Ошибки в task_*

Проверить контракты:
```sql
-- Проверка наличия всех полей в context
SELECT 
  job_id,
  file_name,
  billing_polza,
  billing_neuro,
  chunks_total,
  chunks_done
FROM document_jobs
WHERE job_id = 9001;
```

---

## 📝 Changelog

### 2026-03-28
- ✅ Рефакторинг sub_get_context (1 SQL вместо 3)
- ✅ Добавлена идемпотентность в sub_notify
- ✅ Обновлён task_start_processing (прогресс 0%)
- ✅ Добавлена валидация в main_send_message
- ✅ Добавлено логирование результатов

---

## 📞 Контакты

- **Владелец:** Алексей bigalex
- **Email:** alexei.bigalex@yandex.ru
- **Telegram:** @bigalex
