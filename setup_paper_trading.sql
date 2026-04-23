-- Виртуальный портфель
CREATE TABLE IF NOT EXISTS virtual_portfolio (
    id SERIAL PRIMARY KEY,
    cash_balance NUMERIC DEFAULT 1000000.0, -- Начнем с 1 млн рублей
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Открытые позиции
CREATE TABLE IF NOT EXISTS open_positions (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id),
    quantity INTEGER NOT NULL,
    entry_price NUMERIC NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- История сделок
CREATE TABLE IF NOT EXISTS trade_history (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id),
    side VARCHAR(10), -- BUY, SELL
    quantity INTEGER,
    price NUMERIC,
    pnl NUMERIC, -- Прибыль/убыток (для закрывающих сделок)
    reason TEXT, -- Почему вошли/вышли (сигнал от ИИ)
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Инициализация баланса, если его нет
INSERT INTO virtual_portfolio (id, cash_balance) 
SELECT 1, 1000000.0 WHERE NOT EXISTS (SELECT 1 FROM virtual_portfolio WHERE id = 1);
