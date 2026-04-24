-- Глубокое обслуживание БД торговой системы
-- Выполняется по воскресеньям для оптимизации производительности

-- 1. Пересборка индексов (устраняет раздувание/bloat)
REINDEX TABLE trading.journal;
REINDEX TABLE trading.orders;
REINDEX TABLE trading.ai_call_log;
REINDEX TABLE trading.ai_io_debug_log;
REINDEX TABLE trading.ai_jobs;

-- 2. Полная очистка и переупаковка данных
VACUUM FULL trading.journal;
VACUUM FULL trading.orders;
VACUUM FULL trading.ai_call_log;
VACUUM FULL trading.ai_jobs;

-- 3. Обновление статистики для планировщика запросов
ANALYZE trading.journal;
ANALYZE trading.orders;
ANALYZE trading.ai_call_log;
ANALYZE trading.ai_jobs;
ANALYZE trading.portfolio;
ANALYZE trading.position;
