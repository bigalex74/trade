-- ============================================
-- НАСТРОЙКА ТЕСТОВОГО ОКРУЖЕНИЯ
-- ============================================
-- Запустите этот скрипт один раз для создания тестовых данных
-- ============================================

-- ============================================
-- 1. Создание тестовой задачи
-- ============================================
SELECT '=== Создание тестовой задачи ===' as step;

INSERT INTO document_jobs (file_name, status, billing_polza, billing_neuro, translated_file) 
VALUES (
  'Тестовый документ.pdf',
  'processing',
  '100.50',
  '50.25',
  'Тестовый документ_ru.pdf'
)
RETURNING id;

-- Сохраняем ID для дальнейшего использования
-- \set TEST_JOB_ID LASTVAL()

-- ============================================
-- 2. Активация задачи в job_current
-- ============================================
SELECT '=== Активация задачи ===' as step;

-- Вставляем ссылку на созданную задачу
INSERT INTO job_current (job_id, current_arc, count_done_chunks, error_text, count_error_chunks) 
VALUES (
  (SELECT id FROM document_jobs WHERE file_name = 'Тестовый документ.pdf' ORDER BY id DESC LIMIT 1),
  1,
  5,
  NULL,
  0
);

-- ============================================
-- 3. Создание тестовых чанков
-- ============================================
SELECT '=== Создание чанков ===' as step;

INSERT INTO document_chunks (job_id, chunk_index, status, text, translated_text) 
SELECT 
  (SELECT id FROM document_jobs WHERE file_name = 'Тестовый документ.pdf' ORDER BY id DESC LIMIT 1),
  i,
  CASE WHEN i <= 5 THEN 'done' ELSE 'pending' END,
  'Тестовый текст чанка ' || i,
  CASE WHEN i <= 5 THEN 'Translated chunk ' || i ELSE NULL END
FROM generate_series(1, 10) AS i;

-- ============================================
-- 4. Добавление Telegram чата для тестов
-- ============================================
SELECT '=== Добавление Telegram чата ===' as step;

-- ЗАМЕНИТЕ 'YOUR_CHAT_ID' на реальный ID вашего Telegram чата
-- Узнать chat_id можно через бота @userinfobot
INSERT INTO telegram_chats (chat) 
VALUES ('YOUR_CHAT_ID_HERE')  -- <-- ЗАМЕНИТЬ!
ON CONFLICT (chat) DO NOTHING;

-- Проверка
SELECT * FROM telegram_chats;

-- ============================================
-- 5. Проверка тестовых данных
-- ============================================
SELECT '=== Проверка данных ===' as step;

-- Задача
SELECT id, file_name, status, billing_polza, billing_neuro 
FROM document_jobs 
ORDER BY id DESC 
LIMIT 1;

-- Активная задача
SELECT jc.job_id, dj.file_name, jc.count_done_chunks
FROM job_current jc
JOIN document_jobs dj ON jc.job_id = dj.id;

-- Чанки
SELECT 
  job_id,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE status = 'done') as done
FROM document_chunks 
GROUP BY job_id;

-- ============================================
-- ГОТОВО!
-- ============================================
SELECT '=== ТЕСТОВОЕ ОКРУЖЕНИЕ ГОТОВО ===' as result;
SELECT 'Теперь запустите: docker exec -i n8n-docker-db-1 psql -U n8n_user -d n8n_database -f /home/user/test_send_message.sql' as next_step;
