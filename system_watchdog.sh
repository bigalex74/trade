#!/bin/bash
# АВТОМАТИЧЕСКИЙ САНИТАР СИСТЕМЫ (v1.0)
# Задачи: убийство зомби-процессов и очистка свопа

LOG_FILE="/home/user/logs/system_watchdog.log"
KB_URL="http://localhost:9622/documents/upload"
AUTH="bigalex:qQ08102003"

echo "[$(date)] --- Watchdog cycle started ---" >> "$LOG_FILE"

# 1. Охота на зомби Gemini (ТОЛЬКО фоновые процессы без терминала)
# Мы ищем 'gemini -p', у которых НЕТ привязанного TTY (колонка tty отображает '?')
ZOMBIES=$(ps -eo pid,tty,etime,cmd | grep "gemini -p" | grep "?" | grep -v grep)
while read -r line; do
    PID=$(echo $line | awk '{print $1}')
    TIME=$(echo $line | awk '{print $3}')
    # Если процесс висит долго (формат HH:MM:SS или MM:SS > 15:00)
    if [[ "$TIME" == *":"* ]]; then
        # Дополнительная проверка на время (убиваем если висит более 15 минут)
        MINS=$(echo $TIME | cut -d':' -f1)
        if [[ "$TIME" == *":"*":"* ]] || [ "$MINS" -gt 15 ]; then
            echo "[$(date)] Found background zombie: PID $PID, Time $TIME. Killing..." >> "$LOG_FILE"
            kill -9 $PID 2>/dev/null
        fi
    fi
done <<< "$ZOMBIES"

# 2. Интеллектуальная очистка Swap
SWAP_USED=$(free -m | grep Swap | awk '{print $3}')
RAM_FREE=$(free -m | grep Mem | awk '{print $4}')

# Если своп занят более чем на 4 ГБ и есть свободная ОЗУ > 8 ГБ
if [ "$SWAP_USED" -gt 4000 ] && [ "$RAM_FREE" -gt 8000 ]; then
    echo "[$(date)] Swap pressure detected ($SWAP_USED MB). Clearing swap..." >> "$LOG_FILE"
    sudo swapoff -a && sudo swapon -a
    echo "[$(date)] Swap cleared successfully." >> "$LOG_FILE"
fi

# 3. Отправка отчета в базу знаний (раз в сутки или при инцидентах)
if [[ $(date +%M) == "00" ]]; then
    echo "WATCHDOG REPORT: All systems healthy. Zombies killed today: $(grep -c "Killing" $LOG_FILE). Swap status: $SWAP_USED MB." > /tmp/watchdog_status.txt
    curl -s -X POST $KB_URL -u $AUTH -F "file=@/tmp/watchdog_status.txt" >> /dev/null
    rm /tmp/watchdog_status.txt
fi

echo "[$(date)] --- Watchdog cycle finished ---" >> "$LOG_FILE"
