# ARCHITECTURE AND FEATURES: MOEX AI LEAGUE (v3.2)

## 1. Multi-Division Infrastructure
The fund now operates in two independent divisions using the same Core Intelligence Engine:
*   **MOEX Division:** Russian Equities (RUB), operates during exchange hours.
*   **Crypto Division:** Crypto Spot (USD), operates 24/7.

## 2. Advanced Execution & Order Flow
*   **Limit Order Protocol:** Support for `limit_buy`, `limit_sell`, `stop_loss`.
*   **Short Selling:** Full support for short positions and margin tracking.
*   **Order Matching Engine:** Local биржевое ядро (`order_matching_engine.py`) that matches pending orders against real-time data every minute.

## 3. Reporting Cycle (Sync)
*   **T+00:** MOEX Hourly Performance Chart.
*   **T+30:** Crypto Hourly Performance Chart.
*   **00:00:** Universal Daily Audit & Capital Reallocation.

## 4. Intelligent Risk Control 2.1
*   **Dynamic Lot Sizing:** ATR-based position sizing for volatility parity.
*   **Regime Classifier:** Market Breadth (% stocks > SMA50) determines Bull/Bear state.
*   **News Oracle:** Sentiment analysis from Gemini Flash feeds into Risk Officer.

## 5. Technology Stack
*   **DB:** PostgreSQL 16 (Databases: `market_research`, `crypto_research`).
*   **AI:** Gemini 3.1 Pro (Elite), 3.0 Flash (Fast), Ollama 3.2 (Fallback).
*   **Frontend:** FastAPI + Tailwind + Telegram WebApp SDK.
