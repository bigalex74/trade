-- Создание БД (выполняется отдельно, если нужно)
-- CREATE DATABASE trading_core;

-- Инструменты
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) UNIQUE NOT NULL,
    name TEXT,
    market VARCHAR(20) DEFAULT 'MOEX',
    asset_type VARCHAR(20), -- stock, bond, index
    is_active BOOLEAN DEFAULT TRUE
);

-- Рыночные данные (OHLCV)
CREATE TABLE IF NOT EXISTS market_data (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    UNIQUE(asset_id, timestamp)
);

-- Обучение и база знаний
CREATE TABLE IF NOT EXISTS ai_learning_notes (
    id SERIAL PRIMARY KEY,
    topic TEXT,
    content TEXT,
    source TEXT,
    importance INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Роли (пример)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'trading_bot') THEN
        CREATE ROLE trading_bot WITH LOGIN PASSWORD 'temporary_pass';
    END IF;
END $$;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_bot;
