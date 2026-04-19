# Infisical: Secrets Management Guide

## 🌐 Доступ и локация
- **UI (Панель управления)**: [https://secrets.bigalexn8n.ru](https://secrets.bigalexn8n.ru)
- **Локальный порт**: `8083` (проксируется через Caddy)
- **Директория установки**: `/home/user/infisical`
- **Проект (Project ID)**: `1d44cf0c-94b5-4e64-bccd-9c4da8843fec`

## 🔐 Автоматизация (Machine Identity)
Система настроена на работу без логина и пароля через Client ID и Client Secret. 
Переменные `INFISICAL_MACHINE_IDENTITY_ID` и `INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET` добавлены в `/home/user/.bashrc`.

## 🛠 Работа с CLI
Для запуска любого приложения с подгрузкой секретов из облака используйте:
```bash
infisical run --domain https://secrets.bigalexn8n.ru --env dev -- <ваша_команда>
```

### Примеры:
1. **Запуск n8n**: `infisical run -- n8n start`
2. **Запуск Docker Compose**: `infisical run -- docker compose up -d`
3. **Запуск FastAPI**: `infisical run -- python main.py`

## 📁 Перенос секретов
Все текущие секреты n8n и telegram-apps уже импортированы в проект `MainInfrastructure` в окружение `dev`.

## 🗓 План обслуживания
- **22 апреля 2026 г.**: Удалить содержимое файла `/home/user/n8n-docker/.env` (оставить только пустые ключи для примера) для обеспечения полной безопасности.
