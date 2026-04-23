#!/usr/bin/env python3
import psycopg2
import os
import json
import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone
import time

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": "crypto_research",
    "user": os.getenv("DB_USER", "n8n_user"),
    "password": os.getenv("DB_PASSWORD", "n8n_db_password"),
}

TICKERS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

def get_db_connection(): return psycopg2.connect(**DB_CONFIG)

def calculate_technical_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        df.ta.smma(length=13, offset=8, append=True, col_names=("AL_JAW",))
        df.ta.smma(length=8, offset=5, append=True, col_names=("AL_TEETH",))
        df.ta.smma(length=5, offset=3, append=True, col_names=("AL_LIPS",))
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.obv(append=True) # Добавлено для VSA
        df.ta.supertrend(period=7, multiplier=3, append=True) # Добавлено для трендов
        df.ta.stoch(high='high', low='low', close='close', append=True)
        df.ta.tsi(fast=13, slow=25, signal=13, append=True)
        df.ta.rvi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.donchian(lower_length=20, upper_length=20, append=True)
        df.ta.cksp(p=10, x=1, q=9, append=True)
        df.ta.adx(high='high', low='low', close='close', append=True)
        df.ta.chop(length=14, append=True)
        df.ta.psar(af=0.02, max_af=0.2, append=True)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.wma(length=20, append=True)
        try: df.ta.vwap(append=True)
        except: pass
        ichimoku, _ = df.ta.ichimoku()
        if ichimoku is not None: df = pd.concat([df, ichimoku], axis=1)

        df['fractal_up'] = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(2)) & \
                           (df['high'] > df['high'].shift(-1)) & (df['high'] > df['high'].shift(-2))
        df['fractal_down'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(2)) & \
                             (df['low'] < df['low'].shift(-1)) & (df['low'] < df['low'].shift(-2))

        last_row = df.iloc[-1].to_dict()
        clean = {}
        for k, v in last_row.items():
            if k in ['open', 'high', 'low', 'close', 'volume', 'period_start']: continue
            if pd.isna(v): continue
            new_key = k.replace("BBU_20_2.0", "BB_UP").replace("BBL_20_2.0", "BB_LOW").replace("BBM_20_2.0", "BB_MID")
            new_key = new_key.replace("CKSPl_10_1_9", "CK_STOP_LONG").replace("CKSPs_10_1_9", "CK_STOP_SHORT")
            new_key = new_key.replace("SUPERT_7_3.0", "SUPERTREND").replace("SUPERTd_7_3.0", "SUPERTREND_DIR")
            if isinstance(v, (bool, pd.BooleanDtype)): clean[new_key] = bool(v)
            elif isinstance(v, (float, int)): clean[new_key] = float(v)
            else: clean[new_key] = str(v)
        return clean
    except Exception as e:
        return {"error": str(e)}

def fetch_and_store_crypto_data():
    print(f"[{datetime.now()}] Starting Crypto Data Pipeline...")
    exchange = ccxt.binance()
    conn = get_db_connection()
    
    # 1. Update instrument references
    with conn.cursor() as cur:
        for ticker in TICKERS:
            cur.execute("""
                INSERT INTO ref.instrument (secid, engine, market, board, instrument_group, issuer_name, active)
                VALUES (%s, 'crypto', 'spot', 'binance', 'coin', %s, true)
                ON CONFLICT (engine, market, board, secid) DO NOTHING
            """, (ticker, ticker.split('/')[0]))
        conn.commit()
    
    for ticker in TICKERS:
        try:
            print(f"Fetching data for {ticker}...")
            # Fetch 5m, 1h and 1d candles for context and indicators
            ohlcv_5m = exchange.fetch_ohlcv(ticker, '5m', limit=100)
            ohlcv_1h = exchange.fetch_ohlcv(ticker, '1h', limit=100)
            ohlcv_1d = exchange.fetch_ohlcv(ticker, '1d', limit=100)
            
            if not ohlcv_5m or not ohlcv_1h or not ohlcv_1d: continue
            
            # Format to DataFrame
            df_5m = pd.DataFrame(ohlcv_5m, columns=['period_start', 'open', 'high', 'low', 'close', 'volume'])
            df_1h = pd.DataFrame(ohlcv_1h, columns=['period_start', 'open', 'high', 'low', 'close', 'volume'])
            df_1d = pd.DataFrame(ohlcv_1d, columns=['period_start', 'open', 'high', 'low', 'close', 'volume'])
            
            for df in [df_5m, df_1h, df_1d]:
                df['period_start'] = pd.to_datetime(df['period_start'], unit='ms')
                df.set_index('period_start', inplace=True)
            
            # Calculate Indicators
            inds_5m = calculate_technical_indicators(df_5m)
            
            # ШАГ 2: Генерация графиков Vision (на базе 5м окна)
            from chart_generator import generate_technical_chart
            generate_technical_chart(df_5m, ticker)

            inds_1h = calculate_technical_indicators(df_1h)
            inds_1d = calculate_technical_indicators(df_1d)
            
            # Prepare rows for upsert
            last_5m = df_5m.iloc[-1]; last_1h = df_1h.iloc[-1]; last_1d = df_1d.iloc[-1]
            
            change_5m = float(last_5m['close'] - last_5m['open'])
            pct_5m = float((change_5m / last_5m['open']) * 100) if last_5m['open'] else 0.0
            
            change_1h = float(last_1h['close'] - last_1h['open'])
            pct_1h = float((change_1h / last_1h['open']) * 100) if last_1h['open'] else 0.0
            
            change_1d = float(last_1d['close'] - last_1d['open'])
            pct_1d = float((change_1d / last_1d['open']) * 100) if last_1d['open'] else 0.0

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO analytics.trader_market_windows (
                        secid, engine, market, board, window_key, period_start, period_end,
                        open, high, low, close, volume, source_interval, is_closed, change_abs, change_pct, indicators, updated_at
                    ) VALUES 
                    (%s, 'crypto', 'spot', 'binance', 'current_5m', %s, %s, %s, %s, %s, %s, %s, '5m', false, %s, %s, %s, NOW()),
                    (%s, 'crypto', 'spot', 'binance', 'current_hour', %s, %s, %s, %s, %s, %s, %s, '1h', false, %s, %s, %s, NOW()),
                    (%s, 'crypto', 'spot', 'binance', 'current_day', %s, %s, %s, %s, %s, %s, %s, '1d', false, %s, %s, %s, NOW())
                    ON CONFLICT (secid, window_key) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close, volume=EXCLUDED.volume,
                        change_abs=EXCLUDED.change_abs, change_pct=EXCLUDED.change_pct, indicators=EXCLUDED.indicators, updated_at=NOW()
                """, (
                    ticker, str(df_5m.index[-1]), str(df_5m.index[-1]), float(last_5m['open']), float(last_5m['high']), float(last_5m['low']), float(last_5m['close']), float(last_5m['volume']), change_5m, pct_5m, json.dumps(inds_5m),
                    ticker, str(df_1h.index[-1]), str(df_1h.index[-1]), float(last_1h['open']), float(last_1h['high']), float(last_1h['low']), float(last_1h['close']), float(last_1h['volume']), change_1h, pct_1h, json.dumps(inds_1h),
                    ticker, str(df_1d.index[-1]), str(df_1d.index[-1]), float(last_1d['open']), float(last_1d['high']), float(last_1d['low']), float(last_1d['close']), float(last_1d['volume']), change_1d, pct_1d, json.dumps(inds_1d)
                ))
            conn.commit()
            time.sleep(1) # Rate limit protection
            
        except Exception as e:
            print(f"Failed to fetch/process {ticker}: {e}")
            
    conn.close()
    print("Crypto pipeline completed.")

if __name__ == "__main__":
    fetch_and_store_crypto_data()
