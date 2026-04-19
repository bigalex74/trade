# 🧪 ТЕСТИРОВАНИЕ WORKFLOW "Send Message"

## 📋 План тестирования

### 1. Юнит-тесты ✅ (выполнены)
- [x] Все 9 воркфлоу активны
- [x] Все воркфлоу имеют connections
- [x] Credentials настроены корректно
- [x] Триггер на `telegram_send_message` настроен

### 2. Интеграционные тесты ⏳ (ожидают chat_id)

---

## 🔧 ПОДГОТОВКА К ТЕСТИРОВАНИЮ

### Шаг 1: Добавьте ваш Telegram chat_id

1. Откройте @userinfobot в Telegram
2. Нажмите **Start**
3. Скопируйте ваш ID (например: `123456789`)
4. Выполните SQL:

```sql
-- Замените YOUR_CHAT_ID на ваш реальный ID
INSERT INTO telegram_chats (chat) 
VALUES ('YOUR_CHAT_ID')
ON CONFLICT (chat) DO NOTHING;

-- Проверка
SELECT * FROM telegram_chats;
```

### Шаг 2: Создайте тестовую задачу

```sql
-- Создание тестовой задачи
INSERT INTO document_jobs (
  file_name, status, billing_polza, billing_neuro, 
  translated_file, created_at
) VALUES (
  'Тестовый документ.pdf',
  'pending',
  '100.50',
  '50.25',
  'Тестовый документ_ru.pdf',
  NOW() - INTERVAL '1 hour'
) RETURNING id;

-- Активация
INSERT INTO job_current (job_id, current_arc, count_done_chunks) 
VALUES (LASTVAL(), 1, 5)
ON CONFLICT (job_id) DO UPDATE SET count_done_chunks = 5;

-- Чанки (10 шт, 5 готовых)
INSERT INTO document_chunks (job_id, chunk_index, status) 
SELECT LASTVAL(), i, CASE WHEN i <= 5 THEN 'done' ELSE 'pending' END
FROM generate_series(1, 10) AS i
ON CONFLICT (job_id, chunk_index) DO UPDATE SET status = EXCLUDED.status;
```

---

## 🧪 ЗАПУСК ТЕСТОВ

### Вариант 1: Автоматический запуск всех тестов

```bash
docker exec -i n8n-docker-db-1 psql -U n8n_user -d n8n_database -f /home/user/test_send_message_final.sql
```

### Вариант 2: Пошаговый запуск

#### ТЕСТ 1: Создание задачи (🆕)
```sql
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'create_job';
```

**Ожидаемое сообщение:**
```
🆕 Задача создана

📄 Документ: Тестовый документ.pdf

🚀 Обработка начнётся через несколько секунд...
```

---

#### ТЕСТ 2: Начало обработки (▶️)
```sql
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'start_processing';
```

**Ожидаемое сообщение:**
```
▶️ Обработка началась

📄 Документ: Тестовый документ.pdf
🔄 Статус: В процессе
📊 Прогресс: 0% (0/10)
💰 Потрачено: $0.00
⏳ Оценка времени: ~82 часа
```

---

#### ТЕСТ 3: Прогресс (🔄)
```sql
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'processing';
```

**Ожидаемое сообщение:**
```
🔄 Перевод в процессе

📄 Документ: Тестовый документ.pdf
🗓 Старт: 28.03.2026 14:00:00
⏱ Прошло: 00:05:30
📊 Прогресс: ██████████░░░░░░░░░░ 50%
🧩 Текущий чанк: 5/10
💰 Потрачено на Polza.ai: ₽50.25
💰 Потрачено на NeuroAPI: ₽39.70

Сообщение сгенерировано автоматически.
```

---

#### ТЕСТ 4: Ошибка (⚠️)
```sql
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'error_processing';
```

**Ожидаемое сообщение:**
```
⚠️ Ошибка обработки

📄 Документ: Тестовый документ.pdf

❌ Ошибка:
Тестовая ошибка: API timeout

🔁 Повторная попытка через 30 секунд...
```

---

#### ТЕСТ 5: Завершение (✅)
```sql
-- Сначала обновим задачу
UPDATE document_jobs SET finished_at = NOW() WHERE file_name = 'Тестовый документ.pdf';
UPDATE document_chunks SET status = 'done' WHERE job_id = (SELECT id FROM document_jobs WHERE file_name = 'Тестовый документ.pdf');

-- Затем сообщение
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'finish_processing';
```

**Ожидаемое сообщение:**
```
✅ Перевод завершен!

📄 Документ (исходный): Тестовый документ.pdf
📄 Документ (с переводом): Тестовый документ_ru.pdf

💰 Итоговая стоимость Polza.ai: ₽50.25
💰 Итоговая стоимость NeuroAPI: $0.50 (₽39.70)

🗓 Старт: 28.03.2026 14:00:00
⏱ Переведено за: 00:05:30 (чч:мм:сс)

🔢 Чанков переведено: 10
⌛ Среднее время перевода 1 чанка: 33 сек.
💰 Средняя стоимость 1 чанка ≈ ₽9.00

Сообщение сгенерировано автоматически.
```

---

#### ТЕСТ 6: Остановка с кнопкой (🚨)
```sql
INSERT INTO telegram_send_message (chat_id, message) 
SELECT (SELECT chat::bigint FROM telegram_chats LIMIT 1), 'stop_processing';
```

**Ожидаемое сообщение:**
```
🚨 Перевод остановлен

📄 Документ: Тестовый документ.pdf

⛔ Обработка приостановлена.
Для повтора нажми на кнопку )

[🔁 Повторить] (кнопка)
```

---

## ✅ ПРОВЕРКА РЕЗУЛЬТАТОВ

### В Telegram
Проверьте, что получили 6 сообщений с правильным форматированием:
- [ ] 🆕 Задача создана
- [ ] ▶️ Обработка началась
- [ ] 🔄 Перевод в процессе (с прогресс-баром)
- [ ] ⚠️ Ошибка обработки
- [ ] ✅ Перевод завершен (с итогами)
- [ ] 🚨 Перевод остановлен (с кнопкой)

### В БД
```sql
-- Проверка отправленных сообщений
SELECT 
  id,
  chat_id,
  message,
  type,
  status,
  message_id,
  created_at
FROM telegram_send_message 
ORDER BY id DESC
LIMIT 10;

-- Статистика
SELECT 
  message as type,
  COUNT(*) as count,
  MAX(created_at) as last_message
FROM telegram_send_message 
GROUP BY message;
```

---

## 🐛 TROUBLESHOOTING

### Сообщение не пришло

1. Проверьте, что chat_id добавлен:
   ```sql
   SELECT * FROM telegram_chats;
   ```

2. Проверьте, что workflow активен:
   ```sql
   SELECT name, active FROM workflow_entity WHERE name = 'Send Message';
   ```

3. Проверьте логи n8n:
   ```bash
   docker logs n8n-docker-n8n-1 2>&1 | tail -100
   ```

### Ошибка "Could not find SharedWorkflow"

```sql
-- Добавьте запись в shared_workflow
INSERT INTO shared_workflow ("workflowId", "projectId", role)
SELECT id, 'laKLUPkuQseBWQhm', 'workflow:owner'
FROM workflow_entity WHERE name = 'Send Message';

-- Перезапустите n8n
docker restart n8n-docker-n8n-1
```

### Workflow не активируется

```bash
# Проверьте логи
docker logs n8n-docker-n8n-1 2>&1 | grep -i "error\|fail"

# Перезапустите n8n
docker restart n8n-docker-n8n-1
```

---

## 📊 Метрики успеха

| Метрика | Ожидаемо | Фактически |
|---------|----------|------------|
| Воркфлоу активны | 9/9 | ✓ 9/9 |
| Связи есть | 9/9 | ✓ 9/9 |
| Credentials | Настроены | ✓ Настроены |
| Сообщения в Telegram | 6 | ⏳ Ожидает chat_id |
| Форматирование | HTML | ⏳ Ожидает тест |
| Кнопка в Stop | Есть | ⏳ Ожидает тест |

---

**Готов к запуску тестов после добавления chat_id!** 🚀
