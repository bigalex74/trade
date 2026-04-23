# Перенос торгового проекта в отдельную папку

Дата: 2026-04-23

## Итог

Торговый проект перенесен из загрязненного домашнего корня в чистую папку:

- новый корень проекта: `/home/user/trade`
- git-репозиторий проекта: `/home/user/trade/.git`
- ветка: `master`
- remote: `git@github-trade:bigalex74/trade.git`

Старый git-корень `/home/user/.git` не удален, а архивирован:

- `/home/user/.git-root-trade-archive-20260423043744`

После архивации `/home/user` больше не является git-репозиторием. Это убирает из `git status` домашний мусор: пользовательские настройки, n8n-файлы, временные JSON, MCP-папки, загрузки и другие не относящиеся к торговому проекту файлы.

## Что осталось снаружи проекта намеренно

Эти пути не переносились в git-папку, потому что это runtime-окружение сервера, секреты, логи или внешние рабочие данные:

- `/home/user/trading_venv`
- `/home/user/.env.trading`
- `/home/user/logs`
- `/home/user/gemini-trader-home`
- `/home/user/gemini-trader-workdir`
- `/home/user/lightrag-algo`
- `/home/user/project_backup`

Код теперь должен ссылаться на проектные скрипты через путь относительно своего расположения, а не через `/home/user/<script>.py`.

## Что изменено в коде

- Cron-wrapper'ы получили `PROJECT_DIR`, вычисляемый от директории самого скрипта.
- `ai_paper_trader.py`, `ai_crypto_trader.py`, `ai_job_dispatcher.py` используют локальный `BASE_DIR` для файлов проекта и runner-скриптов.
- `run_ai_job_dispatcher.sh` передает dispatcher'у пути к worker'у и runner'ам из `/home/user/trade`.
- `manage_traders.sh`, `manage_crypto_traders.sh`, генераторы и crypto-runner'ы переведены на новый project root.
- Smoke-тесты теперь запускаются из `/home/user/trade` и используют проектные scripts/tests.
- `backup_project.sh` по умолчанию архивирует текущий проектный каталог, а не весь `/home/user`.
- В `test_ai_watchdog.py` путь к `manage_traders.sh` стал относительным к проекту; Telegram-заголовок watchdog-сообщения переведен на русский.

## Cron

Торговые cron-задачи переключены на `/home/user/trade/...`.

Сохраненный backup crontab перед миграцией:

- `/tmp/crontab.before-trade-root-migration-20260423043535`

n8n-cron-задачи не менялись, потому что это отдельный проект. Отключенная legacy-строка `run_moex_collector.sh` также оставлена как неактивный комментарий.

## Проверки

Выполнены проверки после переноса:

- `bash -n` для всех shell-скриптов проекта
- Python compile без записи `.pyc`: 45 файлов
- `tests/run_tuning_phase1_phase2_smoke.sh`
- `tests/run_tuning_phase3_phase4_smoke.sh`
- `tests/run_tuning_phase5_phase9_smoke.sh`
- dry-run `run_ai_trader_once.sh` с fake Gemini
- dry-run `run_matching_engine_once.sh`
- `run_ai_job_dispatcher.sh` с одним tick
- `run_ai_dispatcher_interval_analyzer.sh --hours 1`
- `git diff --check`

Все проверки завершились успешно.

## Операционное правило

Дальше рабочий каталог для торгового проекта всегда:

```bash
cd /home/user/trade
```

Новые скрипты, docs, тесты и git-коммиты нужно делать только внутри `/home/user/trade`. Старые дубликаты файлов в `/home/user` не являются источником истины и не должны использоваться cron'ом для торгового проекта.
