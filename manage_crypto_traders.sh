#!/bin/bash
# Мастер-контроллер Crypto Лиги

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRADERS_DIR="${PROJECT_DIR}/traders/crypto"
LOG_DIR="/home/user/logs/traders"

get_traders() {
    find "$TRADERS_DIR" -maxdepth 1 -type f -name 'run_*.sh' -printf '%f\n' \
        | sed 's/^run_//;s/\.sh$//' \
        | sort
}

start_trader() {
    local TRADER=$1
    local DEBUG=$2
    local TRADER_FILE="$TRADERS_DIR/run_$TRADER.sh"
    
    if [ ! -f "$TRADER_FILE" ]; then
        echo "[ ERROR ] Trader $TRADER not found."
        return
    fi

    PID=$(pgrep -f "$TRADER_FILE" | xargs)
    if [ -z "$PID" ]; then
        if [ "$DEBUG" = "debug" ]; then
            echo "[ DEBUG ] Starting $(basename "$TRADER_FILE") in debug mode..."
            DEBUG_MODE="true" nohup bash "$TRADER_FILE" > /dev/null 2>&1 &
        else
            nohup bash "$TRADER_FILE" > /dev/null 2>&1 &
        fi
        echo "[ OK ] $(basename "$TRADER_FILE") started."
    else
        echo "[ SKIP ] $TRADER is already running (PID: $PID)."
    fi
}

stop_trader() {
    local TRADER=$1
    echo "Stopping $TRADER (Crypto)..."
    PID=$(pgrep -f "$TRADERS_DIR/run_$TRADER.sh" | xargs)
    if [ -n "$PID" ]; then
        kill "$PID"
        # Убиваем также активный процесс питона этого трейдера
        pkill -f "ai_crypto_trader.py $TRADER"
        echo "[ OK ] $TRADER stopped."
    else
        echo "[ SKIP ] $TRADER was not running."
    fi
}

status() {
    echo -e "CRYPTO TRADER\tSTATUS\t\tPID\t\tLOG_SIZE"
    echo "------------------------------------------------------------"
    for TRADER in $(get_traders); do
        # Ищем точное совпадение пути скрипта
        PID=$(pgrep -f "$TRADERS_DIR/run_$TRADER.sh" | xargs)
        LOG="/home/user/logs/traders/crypto_$TRADER.log"
        if [ "$TRADER" = "hourly_report" ]; then
             LOG="/home/user/logs/traders/crypto_hourly_report.log"
        fi
        SIZE=$(du -h "$LOG" 2>/dev/null | cut -f1)
        [ -z "$SIZE" ] && SIZE="0"
        
        if [ -n "$PID" ]; then
            # Берем только первый PID для проверки статуса
            FIRST_PID=$(echo $PID | cut -d' ' -f1)
            IS_DEBUG=$(ps -fp "$FIRST_PID" | grep "DEBUG_MODE=true")
            if [ -n "$IS_DEBUG" ]; then
                echo -e "$TRADER\t\tDEBUGGING\t$PID\t\t$SIZE"
            else
                echo -e "$TRADER\t\tRUNNING\t\t$PID\t\t$SIZE"
            fi
        else
            echo -e "$TRADER\t\tSTOPPED\t\t-\t\t$SIZE"
        fi
    done
}

start_all() {
    local DEBUG=$1
    echo "Updating secrets from Infisical..."
    infisical export --env dev --projectId 1d44cf0c-94b5-4e64-bccd-9c4da8843fec --format dotenv > /home/user/.env.trading 2>/dev/null
    
    echo "Starting all Crypto Traders (Debug: $DEBUG)..."
    for TRADER in $(get_traders); do
        if [ "$TRADER" = "hourly_report" ]; then continue; fi
        start_trader "$TRADER" "$DEBUG"
        echo "[ WAIT ] Sleeping 15s to stagger load..."
        sleep 20
    done

    echo "Starting Crypto Hourly Report Worker..."
    PID_H=$(pgrep -f "$TRADERS_DIR/run_hourly_report.sh" | xargs)
    if [ -z "$PID_H" ]; then
        nohup bash "$TRADERS_DIR/run_hourly_report.sh" > /dev/null 2>&1 &
    fi
}

case "$1" in
    start)
        if [ "$2" = "all" ]; then
            start_all "$3"
        elif [ -n "$2" ]; then
            start_trader "$2" "$3"
        else
            start_all
        fi
        ;;
    stop)
        if [ -n "$2" ]; then
            stop_trader "$2"
        else
            echo "Stopping all Crypto Traders..."
            pkill -f "$TRADERS_DIR/run_.*.sh"
            pkill -f "ai_crypto_trader.py"
        fi
        ;;
    status) status ;;
    *) echo "Usage: $0 {start [name] [debug]|stop [name]|status}" ;;
esac
