#!/usr/bin/env python3
import argparse
import sys
import json
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2 import extras
import requests
import pandas as pd
import pandas_ta as ta


DB_CONFIG = {
    "host": "localhost",
    "database": "market_research",
    "user": "n8n_user",
    "password": "n8n_db_password",
}

MOEX_BASE_URL = (
    "https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/"
    "{board}/securities/{ticker}/candles.json"
)
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UTC = timezone.utc
DEFAULT_BACKFILL_START = date(2025, 1, 1)
MOEX_PAGE_SIZE = 500

INTERVAL_CONFIG = {
    "1m": {"moex_interval": 1, "bootstrap_days": 5, "overlap_days": 2},
    "1h": {"moex_interval": 60, "bootstrap_days": 45, "overlap_days": 7},
    "1d": {"moex_interval": 24, "bootstrap_days": 730, "overlap_days": 31},
}

INTRADAY_WINDOW_KEYS = [
    "current_5m",
    "previous_5m",
    "current_hour",
    "previous_hour",
    "current_day",
    "previous_day",
    "current_week",
    "previous_week",
    "current_month",
    "previous_month",
    "year",
]

DAILY_WINDOW_KEYS = [
    "current_day",
    "previous_day",
    "current_week",
    "previous_week",
    "current_month",
    "previous_month",
    "year",
]


@dataclass(frozen=True)
class Instrument:
    secid: str
    engine: str
    market: str
    board: str
    instrument_group: str | None
    issuer_name: str | None


@dataclass(frozen=True)
class Entry:
    period_start: datetime
    period_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    value: Decimal | None
    bars_count: int


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_candle_interval_time
            ON raw.candle(interval_name, candle_time DESC, secid)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics.trader_market_windows (
                secid TEXT NOT NULL,
                engine TEXT NOT NULL,
                market TEXT NOT NULL,
                board TEXT NOT NULL,
                instrument_group TEXT,
                issuer_name TEXT,
                window_key VARCHAR(32) NOT NULL,
                period_start TIMESTAMPTZ NOT NULL,
                period_end TIMESTAMPTZ NOT NULL,
                open NUMERIC,
                high NUMERIC,
                low NUMERIC,
                close NUMERIC,
                volume NUMERIC,
                value NUMERIC,
                bars_count INTEGER NOT NULL DEFAULT 0,
                source_interval VARCHAR(16) NOT NULL,
                is_closed BOOLEAN NOT NULL DEFAULT FALSE,
                change_abs NUMERIC,
                change_pct NUMERIC,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (secid, window_key)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trader_market_windows_window_key
            ON analytics.trader_market_windows(window_key)
            """
        )
        cur.execute(
            """
            CREATE OR REPLACE VIEW analytics.trader_market_windows_v AS
            WITH instrument_ref AS (
                SELECT DISTINCT ON (secid)
                    instrument_id,
                    secid,
                    engine,
                    market,
                    board,
                    instrument_group,
                    issuer_name,
                    active
                FROM ref.instrument
                ORDER BY secid, active DESC, updated_at DESC NULLS LAST, instrument_id DESC
            )
            SELECT
                i.instrument_id,
                COALESCE(t.secid, i.secid) AS secid,
                COALESCE(t.engine, i.engine) AS engine,
                COALESCE(t.market, i.market) AS market,
                COALESCE(t.board, i.board) AS board,
                COALESCE(t.instrument_group, i.instrument_group) AS instrument_group,
                COALESCE(t.issuer_name, i.issuer_name) AS issuer_name,
                i.active,
                t.window_key,
                t.period_start,
                t.period_end,
                t.open,
                t.high,
                t.low,
                t.close,
                t.volume,
                t.value,
                t.bars_count,
                t.source_interval,
                t.is_closed,
                t.change_abs,
                t.change_pct,
                t.updated_at
            FROM instrument_ref i
            LEFT JOIN analytics.trader_market_windows t
              ON t.secid = i.secid
            WHERE i.active = TRUE OR t.secid IS NOT NULL
            """
        )
        cur.execute(
            """
            CREATE OR REPLACE VIEW analytics.trader_market_context_v AS
            WITH instrument_ref AS (
                SELECT DISTINCT ON (secid)
                    instrument_id,
                    secid,
                    engine,
                    market,
                    board,
                    instrument_group,
                    issuer_name,
                    active
                FROM ref.instrument
                ORDER BY secid, active DESC, updated_at DESC NULLS LAST, instrument_id DESC
            )
            SELECT
                i.instrument_id,
                i.secid,
                i.engine,
                i.market,
                i.board,
                i.instrument_group,
                i.issuer_name,
                i.active,
                max(t.updated_at) AS updated_at,
                COALESCE(
                    max(CASE WHEN t.window_key = 'current_5m' THEN t.close END),
                    max(CASE WHEN t.window_key = 'current_hour' THEN t.close END),
                    max(CASE WHEN t.window_key = 'current_day' THEN t.close END),
                    max(CASE WHEN t.window_key = 'previous_day' THEN t.close END),
                    max(CASE WHEN t.window_key = 'year' THEN t.close END)
                ) AS current_price,
                max(CASE WHEN t.window_key = 'current_5m' THEN t.change_pct END) AS five_min_change_pct,
                max(CASE WHEN t.window_key = 'current_hour' THEN t.change_pct END) AS hour_change_pct,
                max(CASE WHEN t.window_key = 'current_day' THEN t.change_pct END) AS day_change_pct,
                COALESCE(
                    jsonb_object_agg(
                        t.window_key,
                        jsonb_build_object(
                            'period_start', t.period_start,
                            'period_end', t.period_end,
                            'open', t.open,
                            'high', t.high,
                            'low', t.low,
                            'close', t.close,
                            'volume', t.volume,
                            'value', t.value,
                            'bars_count', t.bars_count,
                            'source_interval', t.source_interval,
                            'is_closed', t.is_closed,
                            'change_abs', t.change_abs,
                            'change_pct', t.change_pct,
                            'updated_at', t.updated_at
                        )
                    ) FILTER (WHERE t.window_key IS NOT NULL),
                    '{}'::jsonb
                ) AS windows
            FROM instrument_ref i
            LEFT JOIN analytics.trader_market_windows t
              ON t.secid = i.secid
            WHERE i.active = TRUE
            GROUP BY
                i.instrument_id,
                i.secid,
                i.engine,
                i.market,
                i.board,
                i.instrument_group,
                i.issuer_name,
                i.active
            """
        )
    conn.commit()


def load_active_instruments(conn) -> list[Instrument]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (secid)
                secid,
                engine,
                market,
                board,
                instrument_group,
                issuer_name
            FROM ref.instrument
            WHERE active = TRUE
            ORDER BY secid, updated_at DESC NULLS LAST, instrument_id DESC
            """
        )
        return [
            Instrument(
                secid=secid,
                engine=engine,
                market=market,
                board=board,
                instrument_group=instrument_group,
                issuer_name=issuer_name,
            )
            for secid, engine, market, board, instrument_group, issuer_name in cur.fetchall()
        ]


def get_last_timestamp(conn, instrument: Instrument, interval_name: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT max(candle_time)
            FROM raw.candle
            WHERE engine = %s
              AND market = %s
              AND board = %s
              AND secid = %s
              AND interval_name = %s
            """,
            (
                instrument.engine,
                instrument.market,
                instrument.board,
                instrument.secid,
                interval_name,
            ),
        )
        row = cur.fetchone()
    return row[0] if row else None


def compute_from_date(interval_name: str, last_timestamp):
    config = INTERVAL_CONFIG[interval_name]
    today_utc = datetime.now(UTC).date()
    bootstrap_floor = max(
        DEFAULT_BACKFILL_START,
        today_utc - timedelta(days=config["bootstrap_days"]),
    )
    if last_timestamp is None:
        return bootstrap_floor
    overlap_start = (
        last_timestamp.astimezone(UTC) - timedelta(days=config["overlap_days"])
    ).date()
    return max(bootstrap_floor, overlap_start)


def fetch_candles(instrument: Instrument, interval_name: str, from_date: date):
    config = INTERVAL_CONFIG[interval_name]
    start = 0
    rows = []
    while True:
        payload = None
        last_error = None
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    MOEX_BASE_URL.format(
                        engine=instrument.engine,
                        market=instrument.market,
                        board=instrument.board,
                        ticker=instrument.secid,
                    ),
                    params={
                        "from": from_date.isoformat(),
                        "interval": config["moex_interval"],
                        "iss.meta": "off",
                        "iss.only": "candles",
                        "start": start,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 3:
                    raise
                time_module.sleep(attempt)

        if payload is None:
            raise last_error

        page_rows = payload.get("candles", {}).get("data", [])
        if not page_rows:
            break

        rows.extend(page_rows)
        if len(page_rows) < MOEX_PAGE_SIZE:
            break
        start += len(page_rows)
    return rows


def parse_moex_ts(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.astimezone(UTC) if raw_value.tzinfo else raw_value.replace(tzinfo=UTC)
    text = str(raw_value)
    if text.endswith("Z"):
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    if "T" in text:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            # MOEX returns MSK without TZ info
            return parsed.replace(tzinfo=MOSCOW_TZ).astimezone(UTC)
        return parsed.astimezone(UTC)
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOSCOW_TZ).astimezone(UTC)


def normalize_decimal(raw_value):
    if raw_value is None:
        return None
    return Decimal(str(raw_value))


def normalize_volume(raw_value):
    if raw_value is None:
        return None
    return int(Decimal(str(raw_value)))


def build_candle_payload(candle_row):
    open_price = normalize_decimal(candle_row[0])
    close_price = normalize_decimal(candle_row[1])
    high_price = normalize_decimal(candle_row[2])
    low_price = normalize_decimal(candle_row[3])
    value = normalize_decimal(candle_row[4])
    volume = normalize_volume(candle_row[5])
    begin_at = parse_moex_ts(candle_row[6])
    end_at = parse_moex_ts(candle_row[7]) if len(candle_row) > 7 else begin_at
    payload = {
        "candle_time": begin_at.isoformat(),
        "begin_at": begin_at.isoformat(),
        "end_at": end_at.isoformat() if end_at else None,
        "open": float(open_price) if open_price is not None else None,
        "close": float(close_price) if close_price is not None else None,
        "high": float(high_price) if high_price is not None else None,
        "low": float(low_price) if low_price is not None else None,
        "value": float(value) if value is not None else None,
        "volume": volume,
        "payload": {
            "open": float(open_price) if open_price is not None else None,
            "close": float(close_price) if close_price is not None else None,
            "high": float(high_price) if high_price is not None else None,
            "low": float(low_price) if low_price is not None else None,
            "value": float(value) if value is not None else None,
            "volume": volume,
            "begin": str(candle_row[6]),
            "end": str(candle_row[7]) if len(candle_row) > 7 else str(candle_row[6]),
        },
    }
    return {
        "candle_time": begin_at,
        "begin_at": begin_at,
        "end_at": end_at,
        "open": open_price,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "value": value,
        "volume": volume,
        "payload": payload,
    }


def store_candles(conn, instrument: Instrument, interval_name: str, candles):
    if not candles:
        return 0

    values = []
    interval_code = INTERVAL_CONFIG[interval_name]["moex_interval"]
    for candle in candles:
        if len(candle) < 7:
            continue
        normalized = build_candle_payload(candle)
        values.append(
            (
                instrument.engine,
                instrument.market,
                instrument.board,
                instrument.secid,
                interval_code,
                interval_name,
                normalized["candle_time"],
                normalized["open"],
                normalized["high"],
                normalized["low"],
                normalized["close"],
                normalized["volume"],
                normalized["value"],
                normalized["begin_at"],
                normalized["end_at"],
                extras.Json(normalized["payload"]),
            )
        )

    if not values:
        return 0

    with conn.cursor() as cur:
        inserted = extras.execute_values(
            cur,
            """
            INSERT INTO raw.candle (
                engine,
                market,
                board,
                secid,
                interval_code,
                interval_name,
                candle_time,
                open,
                high,
                low,
                close,
                volume,
                value,
                begin_at,
                end_at,
                payload
            )
            VALUES %s
            ON CONFLICT (engine, market, board, secid, interval_name, candle_time) DO NOTHING
            RETURNING 1
            """,
            values,
            page_size=500,
            fetch=True,
        )
    return len(inserted)


def run_collect(interval_name: str):
    conn = get_connection()
    ensure_schema(conn)
    instruments = load_active_instruments(conn)
    total_inserted = 0
    processed = 0

    try:
        for instrument in instruments:
            last_timestamp = get_last_timestamp(conn, instrument, interval_name)
            from_date = compute_from_date(interval_name, last_timestamp)
            try:
                candles = fetch_candles(instrument, interval_name, from_date)
            except requests.RequestException as exc:
                print(
                    f"{interval_name} {instrument.secid}: fetch failed from {from_date} - {exc}",
                    file=sys.stderr,
                )
                continue

            inserted = store_candles(conn, instrument, interval_name, candles)
            conn.commit()
            total_inserted += inserted
            processed += 1
            print(
                f"{interval_name} {instrument.secid}: fetched={len(candles)} inserted={inserted} from={from_date}"
            )
    finally:
        conn.close()

    print(
        f"collect summary interval={interval_name} processed={processed} inserted={total_inserted}"
    )


def fetch_entries(conn, interval_name: str, since_ts: datetime, secids: list[str]):
    if not secids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT secid, candle_time, open, high, low, close, volume, value, begin_at, end_at
            FROM raw.candle
            WHERE interval_name = %s
              AND candle_time >= %s
              AND secid = ANY(%s)
            ORDER BY secid, candle_time
            """,
            (interval_name, since_ts, secids),
        )
        rows = cur.fetchall()

    grouped: dict[str, list[Entry]] = {}
    for secid, candle_time, open_price, high_price, low_price, close_price, volume, value, begin_at, end_at in rows:
        grouped.setdefault(secid, []).append(
            Entry(
                period_start=begin_at or candle_time,
                period_end=end_at or candle_time,
                open=Decimal(open_price),
                high=Decimal(high_price),
                low=Decimal(low_price),
                close=Decimal(close_price),
                volume=int(volume or 0),
                value=Decimal(value) if value is not None else None,
                bars_count=1,
            )
        )
    return grouped


def floor_local(dt_value: datetime, minutes: int):
    floored_minute = (dt_value.minute // minutes) * minutes
    return dt_value.replace(minute=floored_minute, second=0, microsecond=0)


def entry_local_date(entry: Entry):
    return entry.period_start.astimezone(MOSCOW_TZ).date()


def entries_in_local_range(entries: Iterable[Entry], start_local: datetime, end_local: datetime):
    selected = []
    for entry in entries:
        ts_local = entry.period_start.astimezone(MOSCOW_TZ)
        if start_local <= ts_local < end_local:
            selected.append(entry)
    return selected


def aggregate_entries(entries: list[Entry]):
    if not entries:
        return None
    ordered = sorted(entries, key=lambda item: item.period_start)
    values = [item.value for item in ordered if item.value is not None]
    return Entry(
        period_start=ordered[0].period_start,
        period_end=ordered[-1].period_end,
        open=ordered[0].open,
        high=max(item.high for item in ordered),
        low=min(item.low for item in ordered),
        close=ordered[-1].close,
        volume=sum(item.volume for item in ordered),
        value=sum(values) if values else None,
        bars_count=sum(item.bars_count for item in ordered),
    )


def month_start(target_date: date):
    return target_date.replace(day=1)


def previous_month_start(target_date: date):
    current_month = month_start(target_date)
    previous_month_end = current_month - timedelta(days=1)
    return previous_month_end.replace(day=1)


def week_start(target_date: date):
    return target_date - timedelta(days=target_date.weekday())


def build_window_row(instrument: Instrument, window_key: str, entry: Entry, source_interval: str, is_closed: bool, indicators: dict = None):
    change_abs = entry.close - entry.open if entry.open is not None and entry.close is not None else None
    change_pct = None
    if change_abs is not None and entry.open not in (None, 0):
        change_pct = (change_abs / entry.open) * Decimal("100")

    return (
        instrument.secid,
        instrument.engine,
        instrument.market,
        instrument.board,
        instrument.instrument_group,
        instrument.issuer_name,
        window_key,
        entry.period_start,
        entry.period_end,
        entry.open,
        entry.high,
        entry.low,
        entry.close,
        entry.volume,
        entry.value,
        entry.bars_count,
        source_interval,
        is_closed,
        change_abs,
        change_pct,
        json.dumps(indicators) if indicators else None
    )


def append_window(rows: list, instrument: Instrument, window_key: str, entry: Entry, source_interval: str, is_closed: bool, indicators: dict = None):
    if entry is None:
        return
    rows.append(build_window_row(instrument, window_key, entry, source_interval, is_closed, indicators))


def calculate_technical_indicators(df):
    """
    Рассчитывает профессиональный набор индикаторов для торговой системы.
    """
    if df is None or len(df) < 50: # Нужно больше свечей для глубоких индикаторов
        return None
    
    try:
        # Обеспечиваем типы
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # 1. Трендовые (Аллигатор Билла Вильямса)
        df.ta.smma(length=13, offset=8, append=True, col_names=("AL_JAW",))
        df.ta.smma(length=8, offset=5, append=True, col_names=("AL_TEETH",))
        df.ta.smma(length=5, offset=3, append=True, col_names=("AL_LIPS",))

        # 2. Осцилляторы и Сила
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.stoch(high='high', low='low', close='close', append=True)
        df.ta.tsi(fast=13, slow=25, signal=13, append=True) # True Strength Index
        df.ta.rvi(length=14, append=True) # Relative Vigor Index
        
        # 3. Волатильность и Каналы
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.donchian(lower_length=20, upper_length=20, append=True) # Donchian Channel
        df.ta.cksp(p=10, x=1, q=9, append=True) # Chande Kroll Stop
        
        # 4. Тренд и Флэт (Chop Zone / Choppiness)
        df.ta.adx(high='high', low='low', close='close', append=True)
        df.ta.chop(length=14, append=True) # Choppiness Index
        df.ta.psar(af=0.02, max_af=0.2, append=True) # Parabolic SAR

        # 5. Средние (MA, EMA, WMA, VWAP)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.wma(length=20, append=True) # Weighted Moving Average
        try:
            df.ta.vwap(append=True) # Volume Weighted Average Price
        except: pass

        # 6. Ишимоку
        ichimoku, _ = df.ta.ichimoku()
        if ichimoku is not None:
            df = pd.concat([df, ichimoku], axis=1)

        # 7. Фракталы
        df['fractal_up'] = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(2)) & \
                           (df['high'] > df['high'].shift(-1)) & (df['high'] > df['high'].shift(-2))
        df['fractal_down'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(2)) & \
                             (df['low'] < df['low'].shift(-1)) & (df['low'] < df['low'].shift(-2))

        # Очистка и фильтрация
        last_row = df.iloc[-1].to_dict()
        clean = {}
        for k, v in last_row.items():
            if k in ['open', 'high', 'low', 'close', 'volume', 'period_start']: continue
            if pd.isna(v): continue
            
            # Переименование для краткости (опционально)
            new_key = k.replace("BBU_20_2.0", "BB_UP").replace("BBL_20_2.0", "BB_LOW").replace("BBM_20_2.0", "BB_MID")
            new_key = new_key.replace("CKSPl_10_1_9", "CK_STOP_LONG").replace("CKSPs_10_1_9", "CK_STOP_SHORT")
            
            if isinstance(v, (bool, pd.BooleanDtype)): clean[new_key] = bool(v)
            elif isinstance(v, (float, int)): clean[new_key] = float(v)
            else: clean[new_key] = str(v)
            
        return clean
    except Exception as e:
        return {"error": str(e)}

def entries_to_df(entries: list[Entry]):
    if not entries: return None
    data = []
    for e in entries:
        data.append({
            "period_start": e.period_start,
            "open": float(e.open),
            "high": float(e.high),
            "low": float(e.low),
            "close": float(e.close),
            "volume": float(e.volume)
        })
    df = pd.DataFrame(data)
    df.set_index("period_start", inplace=True)
    return df

def build_instrument_windows(instrument: Instrument, minute_entries: list[Entry], daily_entries: list[Entry], mode: str):
    rows = []
    daily_entries = sorted(daily_entries, key=lambda item: item.period_start)
    minute_entries = sorted(minute_entries, key=lambda item: item.period_start)

    # Предварительный расчет индикаторов для Daily
    daily_df = entries_to_df(daily_entries)
    daily_indicators = calculate_technical_indicators(daily_df) if daily_df is not None else None

    daily_by_date = {entry_local_date(entry): entry for entry in daily_entries}
    latest_daily_date = max(daily_by_date.keys()) if daily_by_date else None
    latest_minute_date = entry_local_date(minute_entries[-1]) if minute_entries else None

    reference_date = latest_minute_date or latest_daily_date
    if reference_date is None:
        return rows

    current_day_entry = None
    current_day_is_closed = False
    if minute_entries and latest_minute_date == reference_date:
        current_day_minutes = [
            entry for entry in minute_entries if entry_local_date(entry) == reference_date
        ]
        current_day_entry = aggregate_entries(current_day_minutes)
    elif reference_date in daily_by_date:
        current_day_entry = daily_by_date[reference_date]
        current_day_is_closed = True

    previous_day_candidates = [
        entry for entry in daily_entries if entry_local_date(entry) < reference_date
    ]
    previous_day_entry = previous_day_candidates[-1] if previous_day_candidates else None

    append_window(rows, instrument, "current_day", current_day_entry, "1m" if not current_day_is_closed else "1d", current_day_is_closed, daily_indicators)
    append_window(rows, instrument, "previous_day", previous_day_entry, "1d", True)

    current_week_start = week_start(reference_date)
    previous_week_start = current_week_start - timedelta(days=7)
    current_month_start = month_start(reference_date)
    previous_month = previous_month_start(reference_date)
    year_start = date(reference_date.year, 1, 1)

    def aggregate_daily_range(start_date: date, end_date: date):
        return aggregate_entries(
            [
                entry
                for entry in daily_entries
                if start_date <= entry_local_date(entry) < end_date
            ]
        )

    def aggregate_with_current_day(start_date: date, current_entry: Entry | None):
        entries = [
            entry
            for entry in daily_entries
            if start_date <= entry_local_date(entry) < reference_date
        ]
        if current_entry is not None:
            entries.append(current_entry)
        return aggregate_entries(entries)

    current_week_entry = aggregate_with_current_day(current_week_start, current_day_entry)
    previous_week_entry = aggregate_daily_range(previous_week_start, current_week_start)
    current_month_entry = aggregate_with_current_day(current_month_start, current_day_entry)
    previous_month_entry = aggregate_daily_range(previous_month, current_month_start)
    year_entry = aggregate_with_current_day(year_start, current_day_entry)

    append_window(rows, instrument, "current_week", current_week_entry, "mixed", current_day_is_closed, daily_indicators)
    append_window(rows, instrument, "previous_week", previous_week_entry, "1d", True)
    append_window(rows, instrument, "current_month", current_month_entry, "mixed", current_day_is_closed, daily_indicators)
    append_window(rows, instrument, "previous_month", previous_month_entry, "1d", True)
    append_window(rows, instrument, "year", year_entry, "mixed", current_day_is_closed, daily_indicators)

    if mode != "intraday" or not minute_entries:
        return rows

    # Расчет индикаторов для Intraday (на основе 1m, агрегированных в 5m для глубины)
    minute_df = entries_to_df(minute_entries)
    intraday_indicators = None
    if minute_df is not None:
        # Агрегируем в 5m для индикаторов
        resampled_5m = minute_df.resample('5min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        intraday_indicators = calculate_technical_indicators(resampled_5m)

    latest_minute_local = minute_entries[-1].period_start.astimezone(MOSCOW_TZ)
    current_5m_start = floor_local(latest_minute_local, 5)
    previous_5m_start = current_5m_start - timedelta(minutes=5)
    current_hour_start = latest_minute_local.replace(minute=0, second=0, microsecond=0)
    previous_hour_start = current_hour_start - timedelta(hours=1)

    current_5m_entry = aggregate_entries(
        entries_in_local_range(minute_entries, current_5m_start, current_5m_start + timedelta(minutes=5))
    )
    previous_5m_entry = aggregate_entries(
        entries_in_local_range(minute_entries, previous_5m_start, current_5m_start)
    )
    current_hour_entry = aggregate_entries(
        entries_in_local_range(minute_entries, current_hour_start, current_hour_start + timedelta(hours=1))
    )
    previous_hour_entry = aggregate_entries(
        entries_in_local_range(minute_entries, previous_hour_start, current_hour_start)
    )

    append_window(rows, instrument, "current_5m", current_5m_entry, "1m", False, intraday_indicators)
    append_window(rows, instrument, "previous_5m", previous_5m_entry, "1m", True)
    append_window(rows, instrument, "current_hour", current_hour_entry, "1m", False, intraday_indicators)
    append_window(rows, instrument, "previous_hour", previous_hour_entry, "1m", True)

    return rows



def upsert_windows(conn, instrument: Instrument, window_keys: list[str], rows: list[tuple]):
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM analytics.trader_market_windows
            WHERE secid = %s
              AND window_key = ANY(%s)
            """,
            (instrument.secid, window_keys),
        )
        if rows:
            extras.execute_values(
                cur,
                """
                INSERT INTO analytics.trader_market_windows (
                    secid,
                    engine,
                    market,
                    board,
                    instrument_group,
                    issuer_name,
                    window_key,
                    period_start,
                    period_end,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    value,
                    bars_count,
                    source_interval,
                    is_closed,
                    change_abs,
                    change_pct,
                    indicators
                )
                VALUES %s
                ON CONFLICT (secid, window_key) DO UPDATE SET
                    engine = EXCLUDED.engine,
                    market = EXCLUDED.market,
                    board = EXCLUDED.board,
                    instrument_group = EXCLUDED.instrument_group,
                    issuer_name = EXCLUDED.issuer_name,
                    period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    value = EXCLUDED.value,
                    bars_count = EXCLUDED.bars_count,
                    source_interval = EXCLUDED.source_interval,
                    is_closed = EXCLUDED.is_closed,
                    change_abs = EXCLUDED.change_abs,
                    change_pct = EXCLUDED.change_pct,
                    indicators = EXCLUDED.indicators,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
                page_size=100,
            )


def run_refresh(mode: str):
    conn = get_connection()
    ensure_schema(conn)
    instruments = load_active_instruments(conn)
    secids = [instrument.secid for instrument in instruments]
    minute_since = datetime.now(UTC) - timedelta(days=10)
    daily_since = datetime.combine(
        date(datetime.now(MOSCOW_TZ).year - 1, 1, 1),
        time.min,
        tzinfo=MOSCOW_TZ,
    ).astimezone(UTC)

    minute_entries_by_secid = fetch_entries(conn, "1m", minute_since, secids)
    daily_entries_by_secid = fetch_entries(conn, "1d", daily_since, secids)
    window_keys = INTRADAY_WINDOW_KEYS if mode == "intraday" else DAILY_WINDOW_KEYS

    updated_instruments = 0
    stored_windows = 0
    try:
        for instrument in instruments:
            instrument_rows = build_instrument_windows(
                instrument=instrument,
                minute_entries=minute_entries_by_secid.get(instrument.secid, []),
                daily_entries=daily_entries_by_secid.get(instrument.secid, []),
                mode=mode,
            )
            filtered_rows = [row for row in instrument_rows if row[6] in window_keys]
            upsert_windows(conn, instrument, window_keys, filtered_rows)
            updated_instruments += 1
            stored_windows += len(filtered_rows)
            print(f"{mode} {instrument.secid}: stored_windows={len(filtered_rows)}")
        conn.commit()
    finally:
        conn.close()

    print(
        f"refresh summary mode={mode} instruments={updated_instruments} stored_windows={stored_windows}"
    )


def build_parser():
    parser = argparse.ArgumentParser(description="Market research candle/context pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Collect candles from MOEX")
    collect_parser.add_argument(
        "--interval",
        choices=sorted(INTERVAL_CONFIG.keys()),
        required=True,
        help="Target interval stored in raw.candle",
    )

    refresh_parser = subparsers.add_parser(
        "refresh-context", help="Refresh trader multi-timeframe context"
    )
    refresh_parser.add_argument(
        "--mode",
        choices=["daily", "intraday"],
        required=True,
        help="daily refreshes day/week/month/year; intraday adds 5m/hour windows",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "collect":
        run_collect(args.interval)
        return
    if args.command == "refresh-context":
        run_refresh(args.mode)
        return

    parser.error("Unsupported command")


if __name__ == "__main__":
    main()
