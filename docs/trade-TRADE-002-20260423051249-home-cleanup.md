# Уборка домашней папки после переноса проекта

Дата: 2026-04-23

Ветка изменения: `TRADE-002`

Версия проекта после изменения: `0.1.1`

## Цель

После переноса торгового проекта в `/home/user/trade` нужно было убрать старые проектные файлы из `/home/user`, не ломая действующие процессы.

Основной принцип: если есть риск, что перенос или удаление файла может повлиять на систему, файл не трогался.

## Что сделано

Создана архивная папка:

```text
/home/user/trade_legacy_related_20260423
```

Внутри создан `README.md`, где описано назначение папки, структура и форматы файлов.

Удалено из `/home/user`:

- 88 точных дубликатов tracked-файлов, которые уже есть в `/home/user/trade`;
- старые generated `__pycache__` каталоги, связанные с прежним расположением проекта.

Перенесено в архив:

- 34 старые версии проектных файлов, которые отличались от актуальных файлов в `/home/user/trade`;
- старая папка `/home/user/traders`;
- старый архив git-корня `/home/user/.git-root-trade-archive-20260423043744`;
- 39 отдельных старых trading-related файлов: handoff-заметки, старые отчеты, legacy-скрипты и экспериментальные анализаторы.

## Структура архива

```text
/home/user/trade_legacy_related_20260423/modified_project_files
```

Старые отличающиеся версии файлов торгового проекта.

```text
/home/user/trade_legacy_related_20260423/legacy_dirs
```

Старые связанные директории. Сейчас там находится старая папка `traders`.

```text
/home/user/trade_legacy_related_20260423/legacy_loose_files
```

Отдельные старые связанные файлы: `.md`, `.py`, `.sh`.

```text
/home/user/trade_legacy_related_20260423/git_root_archive
```

Архив старого git-корня.

```text
/home/user/trade_legacy_related_20260423/manifests
```

Manifest-файлы со списками удаленных, перенесенных и оставленных файлов.

## Что оставлено в `/home/user`

Не трогались runtime/data и внешние зависимости:

- `/home/user/trade` - рабочий проект;
- `/home/user/trading_venv` - Python-окружение;
- `/home/user/.env.trading` - секреты торгового проекта;
- `/home/user/logs` - runtime-логи;
- `/home/user/gemini-trader-home`;
- `/home/user/gemini-trader-workdir`;
- `/home/user/lightrag-algo`;
- `/home/user/lightrag-kb`;
- `/home/user/n8n-*`;
- `/home/user/telegram-apps` - есть внешние ссылки в n8n-инфраструктуре;
- `/home/user/run_infisical_quiet.sh` - используется активными n8n cron-задачами;
- `/home/user/market_research.db` - data-файл, не удалялся без отдельной проверки;
- `/home/user/charts` - возможные generated/user данные, не удалялись без отдельной проверки.

## Проверки

Проверено после уборки:

- активный crontab продолжает ссылаться на `/home/user/trade` для торгового проекта;
- n8n cron-задачи продолжают использовать `/home/user/run_infisical_quiet.sh`, поэтому этот файл оставлен;
- среди tracked-файлов проекта в `/home/user` остались только сознательно исключенные файлы:
  - `run_infisical_quiet.sh`;
  - `telegram-apps/*`.

## Версия

Изменение не меняет торговую логику и не меняет поведение скриптов проекта, поэтому поднята patch-версия:

```text
0.1.0 -> 0.1.1
```
