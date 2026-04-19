# ИНСТРУКЦИЯ ПО ПЕРЕДАЧЕ КОНТЕКСТА: ЛИГА ТРЕЙДЕРОВ MOEX
*Дата обновления: 18 апреля 2026*

## СТАТУС ПРОЕКТА
Система виртуальной торговли (Paper Trading) полностью настроена. На данный момент работа **ПРИОСТАНОВЛЕНА** по команде пользователя. В "Лиге" участвуют 10 независимых AI-агентов с разным капиталом и стратегиями.

## АРХИТЕКТУРА И ФАЙЛЫ
1. **Торговое ядро:** `/home/user/ai_paper_trader.py`
   - Логика: Принимает имя трейдера, запрашивает RAG (порт 9624) и БД, принимает решение, пишет в `trading.journal`.
2. **Оркестратор (Демон):** `/home/user/ai_trader_daemon.py`
   - Режим: Высокочастотный (каждый агент делает ход раз в ~20-30 сек).
3. **Обертка (Secrets):** `/home/user/run_ai_trading.sh`
   - Важно: Получает `TELEGRAM_BOT_TOKEN` и пароли из **Infisical** (Project ID: 1d44cf0c-94b5-4e64-bccd-9c4da8843fec).
4. **Отчетность:** 
   - `/home/user/ai_hourly_report.py` — Часовой отчет с ASCII-графиком (Nano-Banana).
   - `/home/user/ai_daily_report.py` — Дневной аудит и эволюция (23:55).
5. **Стратегия:** `/home/user/BOT_TRADING_STRATEGY.md` — Текущая "библия" принципов.

## БАЗА ДАННЫХ (PostgreSQL)
- **БД:** `market_research`
- **Схема `trading`:** 
  - `portfolio`: Текущий кеш по 10 агентам (старт: 10 000 RUB).
  - `position`: Открытые лонги.
  - `journal`: Полная история сделок и обоснований.
  - `trader_config`: **Живая память** агентов (learned_traits).

## БАЗЫ ЗНАНИЙ (LightRAG)
1. **kb.bigalexn8n.ru (Порт 9622):** Общий контекст проекта.
2. **algo.bigalexn8n.ru (Порт 9624):** Библиотека трейдинга (40 книг) + логи самоанализа.

## ИНСТРУКЦИЯ ДЛЯ RE-START
Если ты видишь этот файл впервые — **ПРОЧИТАЙ ЕГО ПОЛНОСТЬЮ**. 
Чтобы возобновить работу системы:
1. Выполни команду: `nohup bash /home/user/run_ai_trading.sh daemon > /dev/null 2>&1 &`.
2. Проверь логи: `tail -f /home/user/logs/ai_trader.log`.
3. Убедись, что Infisical CLI авторизован.

## СПИСОК АГЕНТОВ (10)
- VSA_Victor (VSA), Chaos_Bill (Хаос), Elliott_Alex (Волны), Contrarian_Ricardo (Контртренд), Quant_Diana (Квант), PriceAction_Nikita (Уровни), Passive_Palych (Дивиденды), Scalper_Kesha (Скальпинг), Value_Monya (Фундаментал), Index_Tracker (Индекс).
