-- SQL для создания таблиц под AI-агента (Редактора)

-- 1. Таблица стилистических замен
CREATE TABLE IF NOT EXISTS style_replacements (
    id SERIAL PRIMARY KEY,
    bad_word VARCHAR(255) NOT NULL UNIQUE,
    replacement VARCHAR(255) NOT NULL,
    comment TEXT
);

INSERT INTO style_replacements (bad_word, replacement) VALUES 
('опёрся', 'прислонился'),
('упёрся', 'закрепился'),
('тогдашний', 'прежний'),
('мол', 'якобы'),
('является', 'есть'),
('данный', 'этот')
ON CONFLICT (bad_word) DO NOTHING;

-- 2. Таблица истории пояснений
CREATE TABLE IF NOT EXISTS internal_glossary (
    id SERIAL PRIMARY KEY,
    term_ko VARCHAR(255) NOT NULL,
    term_ru VARCHAR(255) NOT NULL,
    explanation TEXT NOT NULL,
    is_explained BOOLEAN DEFAULT TRUE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(term_ko)
);
