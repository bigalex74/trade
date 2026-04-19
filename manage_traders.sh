#!/bin/bash
# Мастер-контроллер Лиги Трейдеров (v2.0)

TRADERS_DIR="/home/user/traders"
LOG_DIR="/home/user/logs/traders"

get_traders() {
    ls "$TRADERS_DIR"/run_*.sh | xargs -n 1 basename | sed 's/run_//;s/.sh//'
}

start_trader() {
    local TRADER=$1
    local DEBUG=$2
    if [ ! -f "$TRADERS_DIR/run_$TRADER.sh" ]; then
        # Попытка найти с другим расширением или похожим именем
        TRADER_FILE=$(ls "$TRADERS_DIR"/run_*.sh | grep -i "$TRADER" | head -n 1)
        if [ -z "$TRADER_FILE" ]; then
            echo "[ ERROR ] Trader $TRADER not found."
            return
        fi
    else
        TRADER_FILE="$TRADERS_DIR/run_$TRADER.sh"
    fi

    PID=$(pgrep -f "$(basename "$TRADER_FILE")")
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
    echo "Stopping $TRADER..."
    PID=$(pgrep -f "run_$TRADER.sh")
    if [ -n "$PID" ]; then
        kill "$PID"
        # Убиваем также активный процесс питона этого трейдера
        pkill -f "ai_paper_trader.py $TRADER"
        echo "[ OK ] $TRADER stopped."
    else
        echo "[ SKIP ] $TRADER was not running."
    fi
}

status() {
    echo -e "TRADER\t\tSTATUS\t\tPID\t\tLOG_SIZE"
    echo "------------------------------------------------------------"
    for TRADER in $(get_traders); do
        PID=$(pgrep -f "run_$TRADER.sh")
        LOG="$LOG_DIR/$TRADER.log"
        SIZE=$(du -h "$LOG" 2>/dev/null | cut -f1)
        [ -z "$SIZE" ] && SIZE="0"
        
        if [ -n "$PID" ]; then
            # Проверяем, не в дебаге ли он
            IS_DEBUG=$(ps -fp "$PID" | grep "DEBUG_MODE=true")
            if [ -n "$IS_DEBUG" ]; then
                echo -e "$TRADER\t\tDEBUGGING\t$PID\t\t$SIZE"
            else
                echo -e "$TRADER\t\tRUNNING\t\t$PID\t\t$SIZE"
            fi
        else
            echo -e "$TRADER\t\tSTOPPED\t\t-\t\t$SIZE"
        fi
    done
    
    # Статус служебных воркеров
    for WORKER in "hourly_report" "matching_engine"; do
        PID=$(pgrep -f "run_${WORKER}.sh")
        LOG="$LOG_DIR/${WORKER}.log"
        SIZE=$(du -h "$LOG" 2>/dev/null | cut -f1)
        [ -z "$SIZE" ] && SIZE="0"
        if [ -n "$PID" ]; then
            echo -e "${WORKER}\tRUNNING\t\t$PID\t\t$SIZE"
        else
            echo -e "${WORKER}\tSTOPPED\t\t-\t\t$SIZE"
        fi
    done
}

start_all() {
    local DEBUG=$1
    echo "Updating secrets from Infisical..."
    infisical export --env dev --projectId 1d44cf0c-94b5-4e64-bccd-9c4da8843fec --format dotenv > /home/user/.env.trading 2>/dev/null
    
    echo "Starting all AI Traders (Debug: $DEBUG)..."
    for TRADER in $(get_traders); do
        start_trader "$TRADER" "$DEBUG"
    done

    echo "Starting Hourly Report Worker..."
    PID=$(pgrep -f "run_hourly_report.sh")
    if [ -z "$PID" ]; then
        nohup bash "$TRADERS_DIR/run_hourly_report.sh" > /dev/null 2>&1 &
    fi

    echo "Starting Order Matching Engine..."
    PID_ME=$(pgrep -f "run_matching_engine.sh")
    if [ -z "$PID_ME" ]; then
        nohup bash "$TRADERS_DIR/run_matching_engine.sh" > /dev/null 2>&1 &
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
            echo "Stopping all Traders..."
            pkill -f "run_.*.sh"
            pkill -f "ai_paper_trader.py"
        fi
        ;;
    status) status ;;
    *) echo "Usage: $0 {start [name] [debug]|stop [name]|status}" ;;
esac
