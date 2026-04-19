#!/bin/bash
# Скрипт автоматического бэкапа Лиги Трейдеров

cd /home/user
git add .
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
git commit -m "backup: Automatic project backup $TIMESTAMP"

# Если есть удаленный репозиторий - пушим
if git remote | grep -q 'origin'; then
    git push origin master
fi

echo "[$TIMESTAMP] Project backup completed."
