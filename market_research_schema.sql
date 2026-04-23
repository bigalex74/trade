--
-- PostgreSQL database dump
--

\restrict V6PodoaVNyDLRDdRhd0XzqKa1hlIRrartiVExUKTROfrTWafIYrXmUQp0ZdjPAN

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: analytics; Type: SCHEMA; Schema: -; Owner: market_owner
--

CREATE SCHEMA analytics;


ALTER SCHEMA analytics OWNER TO market_owner;

--
-- Name: ingest; Type: SCHEMA; Schema: -; Owner: market_owner
--

CREATE SCHEMA ingest;


ALTER SCHEMA ingest OWNER TO market_owner;

--
-- Name: meta; Type: SCHEMA; Schema: -; Owner: market_owner
--

CREATE SCHEMA meta;


ALTER SCHEMA meta OWNER TO market_owner;

--
-- Name: raw; Type: SCHEMA; Schema: -; Owner: market_owner
--

CREATE SCHEMA raw;


ALTER SCHEMA raw OWNER TO market_owner;

--
-- Name: ref; Type: SCHEMA; Schema: -; Owner: market_owner
--

CREATE SCHEMA ref;


ALTER SCHEMA ref OWNER TO market_owner;

--
-- Name: trading; Type: SCHEMA; Schema: -; Owner: n8n_user
--

CREATE SCHEMA trading;


ALTER SCHEMA trading OWNER TO n8n_user;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: instrument_snapshot; Type: TABLE; Schema: analytics; Owner: n8n_user
--

CREATE TABLE analytics.instrument_snapshot (
    snapshot_id bigint NOT NULL,
    engine text NOT NULL,
    market text NOT NULL,
    board text NOT NULL,
    secid text NOT NULL,
    interval_code integer NOT NULL,
    interval_name text NOT NULL,
    snapshot_at timestamp with time zone DEFAULT now() NOT NULL,
    candles_count integer DEFAULT 0 NOT NULL,
    latest_close numeric(20,6),
    change_pct numeric(12,6),
    last_volume numeric(30,6),
    summary_text text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE analytics.instrument_snapshot OWNER TO n8n_user;

--
-- Name: instrument_snapshot_snapshot_id_seq; Type: SEQUENCE; Schema: analytics; Owner: n8n_user
--

ALTER TABLE analytics.instrument_snapshot ALTER COLUMN snapshot_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME analytics.instrument_snapshot_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: latest_snapshot; Type: VIEW; Schema: analytics; Owner: n8n_user
--

CREATE VIEW analytics.latest_snapshot AS
 SELECT DISTINCT ON (engine, market, board, secid, interval_name) snapshot_id,
    engine,
    market,
    board,
    secid,
    interval_code,
    interval_name,
    snapshot_at,
    candles_count,
    latest_close,
    change_pct,
    last_volume,
    summary_text,
    payload
   FROM analytics.instrument_snapshot
  ORDER BY engine, market, board, secid, interval_name, snapshot_at DESC;


ALTER VIEW analytics.latest_snapshot OWNER TO n8n_user;

--
-- Name: market_sentiment; Type: TABLE; Schema: analytics; Owner: n8n_user
--

CREATE TABLE analytics.market_sentiment (
    secid text NOT NULL,
    score numeric(4,2) DEFAULT 0.0 NOT NULL,
    summary text,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE analytics.market_sentiment OWNER TO n8n_user;

--
-- Name: research_digest; Type: TABLE; Schema: analytics; Owner: n8n_user
--

CREATE TABLE analytics.research_digest (
    digest_id bigint NOT NULL,
    report_type text NOT NULL,
    scope text DEFAULT 'moex'::text NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    summary_text text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    knowledge_source text
);


ALTER TABLE analytics.research_digest OWNER TO n8n_user;

--
-- Name: research_digest_digest_id_seq; Type: SEQUENCE; Schema: analytics; Owner: n8n_user
--

ALTER TABLE analytics.research_digest ALTER COLUMN digest_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME analytics.research_digest_digest_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: trader_market_windows; Type: TABLE; Schema: analytics; Owner: n8n_user
--

CREATE TABLE analytics.trader_market_windows (
    secid text NOT NULL,
    engine text NOT NULL,
    market text NOT NULL,
    board text NOT NULL,
    instrument_group text,
    issuer_name text,
    window_key character varying(32) NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume numeric,
    value numeric,
    bars_count integer DEFAULT 0 NOT NULL,
    source_interval character varying(16) NOT NULL,
    is_closed boolean DEFAULT false NOT NULL,
    change_abs numeric,
    change_pct numeric,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    indicators jsonb
);


ALTER TABLE analytics.trader_market_windows OWNER TO n8n_user;

--
-- Name: instrument; Type: TABLE; Schema: ref; Owner: n8n_user
--

CREATE TABLE ref.instrument (
    instrument_id bigint NOT NULL,
    secid text NOT NULL,
    engine text NOT NULL,
    market text NOT NULL,
    board text NOT NULL,
    instrument_group text NOT NULL,
    issuer_name text NOT NULL,
    news_keywords text DEFAULT ''::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ref.instrument OWNER TO n8n_user;

--
-- Name: trader_market_context_v; Type: VIEW; Schema: analytics; Owner: n8n_user
--

CREATE VIEW analytics.trader_market_context_v AS
 WITH instrument_ref AS (
         SELECT DISTINCT ON (instrument.secid) instrument.instrument_id,
            instrument.secid,
            instrument.engine,
            instrument.market,
            instrument.board,
            instrument.instrument_group,
            instrument.issuer_name,
            instrument.active
           FROM ref.instrument
          ORDER BY instrument.secid, instrument.active DESC, instrument.updated_at DESC NULLS LAST, instrument.instrument_id DESC
        )
 SELECT i.instrument_id,
    i.secid,
    i.engine,
    i.market,
    i.board,
    i.instrument_group,
    i.issuer_name,
    i.active,
    max(t.updated_at) AS updated_at,
    COALESCE(max(
        CASE
            WHEN ((t.window_key)::text = 'current_5m'::text) THEN t.close
            ELSE NULL::numeric
        END), max(
        CASE
            WHEN ((t.window_key)::text = 'current_hour'::text) THEN t.close
            ELSE NULL::numeric
        END), max(
        CASE
            WHEN ((t.window_key)::text = 'current_day'::text) THEN t.close
            ELSE NULL::numeric
        END), max(
        CASE
            WHEN ((t.window_key)::text = 'previous_day'::text) THEN t.close
            ELSE NULL::numeric
        END), max(
        CASE
            WHEN ((t.window_key)::text = 'year'::text) THEN t.close
            ELSE NULL::numeric
        END)) AS current_price,
    max(
        CASE
            WHEN ((t.window_key)::text = 'current_5m'::text) THEN t.change_pct
            ELSE NULL::numeric
        END) AS five_min_change_pct,
    max(
        CASE
            WHEN ((t.window_key)::text = 'current_hour'::text) THEN t.change_pct
            ELSE NULL::numeric
        END) AS hour_change_pct,
    max(
        CASE
            WHEN ((t.window_key)::text = 'current_day'::text) THEN t.change_pct
            ELSE NULL::numeric
        END) AS day_change_pct,
    COALESCE(jsonb_object_agg(t.window_key, jsonb_build_object('period_start', t.period_start, 'period_end', t.period_end, 'open', t.open, 'high', t.high, 'low', t.low, 'close', t.close, 'volume', t.volume, 'value', t.value, 'bars_count', t.bars_count, 'source_interval', t.source_interval, 'is_closed', t.is_closed, 'change_abs', t.change_abs, 'change_pct', t.change_pct, 'updated_at', t.updated_at)) FILTER (WHERE (t.window_key IS NOT NULL)), '{}'::jsonb) AS windows
   FROM (instrument_ref i
     LEFT JOIN analytics.trader_market_windows t ON ((t.secid = i.secid)))
  WHERE (i.active = true)
  GROUP BY i.instrument_id, i.secid, i.engine, i.market, i.board, i.instrument_group, i.issuer_name, i.active;


ALTER VIEW analytics.trader_market_context_v OWNER TO n8n_user;

--
-- Name: trader_market_windows_v; Type: VIEW; Schema: analytics; Owner: n8n_user
--

CREATE VIEW analytics.trader_market_windows_v AS
 WITH instrument_ref AS (
         SELECT DISTINCT ON (instrument.secid) instrument.instrument_id,
            instrument.secid,
            instrument.engine,
            instrument.market,
            instrument.board,
            instrument.instrument_group,
            instrument.issuer_name,
            instrument.active
           FROM ref.instrument
          ORDER BY instrument.secid, instrument.active DESC, instrument.updated_at DESC NULLS LAST, instrument.instrument_id DESC
        )
 SELECT i.instrument_id,
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
   FROM (instrument_ref i
     LEFT JOIN analytics.trader_market_windows t ON ((t.secid = i.secid)))
  WHERE ((i.active = true) OR (t.secid IS NOT NULL));


ALTER VIEW analytics.trader_market_windows_v OWNER TO n8n_user;

--
-- Name: lightrag_document_log; Type: TABLE; Schema: ingest; Owner: n8n_user
--

CREATE TABLE ingest.lightrag_document_log (
    document_log_id bigint NOT NULL,
    target_kb text DEFAULT 'tradekb'::text NOT NULL,
    document_type text NOT NULL,
    source_key text NOT NULL,
    source_table text,
    source_pk text,
    document_hash text,
    status text DEFAULT 'published'::text NOT NULL,
    response_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    published_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ingest.lightrag_document_log OWNER TO n8n_user;

--
-- Name: lightrag_document_log_document_log_id_seq; Type: SEQUENCE; Schema: ingest; Owner: n8n_user
--

ALTER TABLE ingest.lightrag_document_log ALTER COLUMN document_log_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME ingest.lightrag_document_log_document_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_cursor; Type: TABLE; Schema: meta; Owner: n8n_user
--

CREATE TABLE meta.workflow_cursor (
    workflow_key text NOT NULL,
    cursor_value text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE meta.workflow_cursor OWNER TO n8n_user;

--
-- Name: candle; Type: TABLE; Schema: raw; Owner: n8n_user
--

CREATE TABLE raw.candle (
    engine text NOT NULL,
    market text NOT NULL,
    board text NOT NULL,
    secid text NOT NULL,
    interval_code integer NOT NULL,
    interval_name text NOT NULL,
    candle_time timestamp with time zone NOT NULL,
    open numeric(20,6),
    high numeric(20,6),
    low numeric(20,6),
    close numeric(20,6),
    volume numeric(30,6),
    value numeric(30,6),
    begin_at timestamp with time zone,
    end_at timestamp with time zone,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    collected_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.candle OWNER TO n8n_user;

--
-- Name: news_instrument_match; Type: TABLE; Schema: raw; Owner: n8n_user
--

CREATE TABLE raw.news_instrument_match (
    news_id bigint NOT NULL,
    instrument_id bigint NOT NULL,
    matched_keywords text DEFAULT ''::text NOT NULL,
    confidence numeric(6,4),
    matched_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.news_instrument_match OWNER TO n8n_user;

--
-- Name: news_item; Type: TABLE; Schema: raw; Owner: n8n_user
--

CREATE TABLE raw.news_item (
    news_id bigint NOT NULL,
    source text NOT NULL,
    external_id text NOT NULL,
    published_at timestamp with time zone,
    title text NOT NULL,
    link text NOT NULL,
    summary text,
    content text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.news_item OWNER TO n8n_user;

--
-- Name: news_item_news_id_seq; Type: SEQUENCE; Schema: raw; Owner: n8n_user
--

ALTER TABLE raw.news_item ALTER COLUMN news_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME raw.news_item_news_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: instrument_instrument_id_seq; Type: SEQUENCE; Schema: ref; Owner: n8n_user
--

ALTER TABLE ref.instrument ALTER COLUMN instrument_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME ref.instrument_instrument_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: daily_stats; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading.daily_stats (
    id integer NOT NULL,
    stat_date date NOT NULL,
    total_value numeric(20,6) NOT NULL,
    cash_balance numeric(20,6) NOT NULL,
    positions_value numeric(20,6) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    trader_name text
);


ALTER TABLE trading.daily_stats OWNER TO n8n_user;

--
-- Name: daily_stats_id_seq; Type: SEQUENCE; Schema: trading; Owner: n8n_user
--

CREATE SEQUENCE trading.daily_stats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE trading.daily_stats_id_seq OWNER TO n8n_user;

--
-- Name: daily_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: trading; Owner: n8n_user
--

ALTER SEQUENCE trading.daily_stats_id_seq OWNED BY trading.daily_stats.id;


--
-- Name: journal; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading.journal (
    id integer NOT NULL,
    secid text NOT NULL,
    action text NOT NULL,
    quantity integer NOT NULL,
    price numeric(20,6) NOT NULL,
    reason text,
    created_at timestamp with time zone DEFAULT now(),
    trader_name text,
    model_id text,
    indicators_snapshot jsonb
);


ALTER TABLE trading.journal OWNER TO n8n_user;

--
-- Name: journal_id_seq; Type: SEQUENCE; Schema: trading; Owner: n8n_user
--

CREATE SEQUENCE trading.journal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE trading.journal_id_seq OWNER TO n8n_user;

--
-- Name: journal_id_seq; Type: SEQUENCE OWNED BY; Schema: trading; Owner: n8n_user
--

ALTER SEQUENCE trading.journal_id_seq OWNED BY trading.journal.id;


--
-- Name: orders; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading.orders (
    id integer NOT NULL,
    trader_name text NOT NULL,
    secid text NOT NULL,
    order_type text NOT NULL,
    quantity integer NOT NULL,
    target_price numeric(20,6) NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    model_id text,
    reason text,
    created_at timestamp with time zone DEFAULT now(),
    filled_at timestamp with time zone
);


ALTER TABLE trading.orders OWNER TO n8n_user;

--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: trading; Owner: n8n_user
--

CREATE SEQUENCE trading.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE trading.orders_id_seq OWNER TO n8n_user;

--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: trading; Owner: n8n_user
--

ALTER SEQUENCE trading.orders_id_seq OWNED BY trading.orders.id;


--
-- Name: portfolio; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading.portfolio (
    id integer NOT NULL,
    cash_balance numeric(20,6) DEFAULT 1000000.0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    trader_name text NOT NULL
);


ALTER TABLE trading.portfolio OWNER TO n8n_user;

--
-- Name: portfolio_id_seq; Type: SEQUENCE; Schema: trading; Owner: n8n_user
--

CREATE SEQUENCE trading.portfolio_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE trading.portfolio_id_seq OWNER TO n8n_user;

--
-- Name: portfolio_id_seq; Type: SEQUENCE OWNED BY; Schema: trading; Owner: n8n_user
--

ALTER SEQUENCE trading.portfolio_id_seq OWNED BY trading.portfolio.id;


--
-- Name: position; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading."position" (
    id integer NOT NULL,
    secid text NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    avg_entry_price numeric(20,6) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    trader_name text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE trading."position" OWNER TO n8n_user;

--
-- Name: position_id_seq; Type: SEQUENCE; Schema: trading; Owner: n8n_user
--

CREATE SEQUENCE trading.position_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE trading.position_id_seq OWNER TO n8n_user;

--
-- Name: position_id_seq; Type: SEQUENCE OWNED BY; Schema: trading; Owner: n8n_user
--

ALTER SEQUENCE trading.position_id_seq OWNED BY trading."position".id;


--
-- Name: trader_config; Type: TABLE; Schema: trading; Owner: n8n_user
--

CREATE TABLE trading.trader_config (
    trader_name text NOT NULL,
    learned_traits text DEFAULT 'Начинай обучение с чистой стратегии.'::text,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE trading.trader_config OWNER TO n8n_user;

--
-- Name: daily_stats id; Type: DEFAULT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.daily_stats ALTER COLUMN id SET DEFAULT nextval('trading.daily_stats_id_seq'::regclass);


--
-- Name: journal id; Type: DEFAULT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.journal ALTER COLUMN id SET DEFAULT nextval('trading.journal_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.orders ALTER COLUMN id SET DEFAULT nextval('trading.orders_id_seq'::regclass);


--
-- Name: portfolio id; Type: DEFAULT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.portfolio ALTER COLUMN id SET DEFAULT nextval('trading.portfolio_id_seq'::regclass);


--
-- Name: position id; Type: DEFAULT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading."position" ALTER COLUMN id SET DEFAULT nextval('trading.position_id_seq'::regclass);


--
-- Name: instrument_snapshot instrument_snapshot_pkey; Type: CONSTRAINT; Schema: analytics; Owner: n8n_user
--

ALTER TABLE ONLY analytics.instrument_snapshot
    ADD CONSTRAINT instrument_snapshot_pkey PRIMARY KEY (snapshot_id);


--
-- Name: market_sentiment market_sentiment_pkey; Type: CONSTRAINT; Schema: analytics; Owner: n8n_user
--

ALTER TABLE ONLY analytics.market_sentiment
    ADD CONSTRAINT market_sentiment_pkey PRIMARY KEY (secid);


--
-- Name: research_digest research_digest_pkey; Type: CONSTRAINT; Schema: analytics; Owner: n8n_user
--

ALTER TABLE ONLY analytics.research_digest
    ADD CONSTRAINT research_digest_pkey PRIMARY KEY (digest_id);


--
-- Name: trader_market_windows trader_market_windows_pkey; Type: CONSTRAINT; Schema: analytics; Owner: n8n_user
--

ALTER TABLE ONLY analytics.trader_market_windows
    ADD CONSTRAINT trader_market_windows_pkey PRIMARY KEY (secid, window_key);


--
-- Name: lightrag_document_log lightrag_document_log_pkey; Type: CONSTRAINT; Schema: ingest; Owner: n8n_user
--

ALTER TABLE ONLY ingest.lightrag_document_log
    ADD CONSTRAINT lightrag_document_log_pkey PRIMARY KEY (document_log_id);


--
-- Name: lightrag_document_log uq_lightrag_target_source; Type: CONSTRAINT; Schema: ingest; Owner: n8n_user
--

ALTER TABLE ONLY ingest.lightrag_document_log
    ADD CONSTRAINT uq_lightrag_target_source UNIQUE (target_kb, source_key);


--
-- Name: workflow_cursor workflow_cursor_pkey; Type: CONSTRAINT; Schema: meta; Owner: n8n_user
--

ALTER TABLE ONLY meta.workflow_cursor
    ADD CONSTRAINT workflow_cursor_pkey PRIMARY KEY (workflow_key);


--
-- Name: candle candle_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.candle
    ADD CONSTRAINT candle_pkey PRIMARY KEY (engine, market, board, secid, interval_name, candle_time);


--
-- Name: news_instrument_match news_instrument_match_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.news_instrument_match
    ADD CONSTRAINT news_instrument_match_pkey PRIMARY KEY (news_id, instrument_id);


--
-- Name: news_item news_item_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.news_item
    ADD CONSTRAINT news_item_pkey PRIMARY KEY (news_id);


--
-- Name: news_item uq_news_source_external; Type: CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.news_item
    ADD CONSTRAINT uq_news_source_external UNIQUE (source, external_id);


--
-- Name: instrument instrument_pkey; Type: CONSTRAINT; Schema: ref; Owner: n8n_user
--

ALTER TABLE ONLY ref.instrument
    ADD CONSTRAINT instrument_pkey PRIMARY KEY (instrument_id);


--
-- Name: instrument uq_instrument_identity; Type: CONSTRAINT; Schema: ref; Owner: n8n_user
--

ALTER TABLE ONLY ref.instrument
    ADD CONSTRAINT uq_instrument_identity UNIQUE (engine, market, board, secid);


--
-- Name: daily_stats daily_stats_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.daily_stats
    ADD CONSTRAINT daily_stats_pkey PRIMARY KEY (id);


--
-- Name: daily_stats daily_stats_trader_name_stat_date_key; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.daily_stats
    ADD CONSTRAINT daily_stats_trader_name_stat_date_key UNIQUE (trader_name, stat_date);


--
-- Name: journal journal_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.journal
    ADD CONSTRAINT journal_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: portfolio portfolio_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.portfolio
    ADD CONSTRAINT portfolio_pkey PRIMARY KEY (trader_name);


--
-- Name: position position_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading."position"
    ADD CONSTRAINT position_pkey PRIMARY KEY (id);


--
-- Name: position position_trader_name_secid_key; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading."position"
    ADD CONSTRAINT position_trader_name_secid_key UNIQUE (trader_name, secid);


--
-- Name: trader_config trader_config_pkey; Type: CONSTRAINT; Schema: trading; Owner: n8n_user
--

ALTER TABLE ONLY trading.trader_config
    ADD CONSTRAINT trader_config_pkey PRIMARY KEY (trader_name);


--
-- Name: idx_digest_generated_at; Type: INDEX; Schema: analytics; Owner: n8n_user
--

CREATE INDEX idx_digest_generated_at ON analytics.research_digest USING btree (generated_at DESC);


--
-- Name: idx_snapshot_lookup; Type: INDEX; Schema: analytics; Owner: n8n_user
--

CREATE INDEX idx_snapshot_lookup ON analytics.instrument_snapshot USING btree (secid, interval_name, snapshot_at DESC);


--
-- Name: idx_trader_market_windows_window_key; Type: INDEX; Schema: analytics; Owner: n8n_user
--

CREATE INDEX idx_trader_market_windows_window_key ON analytics.trader_market_windows USING btree (window_key);


--
-- Name: idx_lightrag_status; Type: INDEX; Schema: ingest; Owner: n8n_user
--

CREATE INDEX idx_lightrag_status ON ingest.lightrag_document_log USING btree (status, published_at DESC);


--
-- Name: idx_candle_interval_time; Type: INDEX; Schema: raw; Owner: n8n_user
--

CREATE INDEX idx_candle_interval_time ON raw.candle USING btree (interval_name, candle_time DESC, secid);


--
-- Name: idx_candle_lookup; Type: INDEX; Schema: raw; Owner: n8n_user
--

CREATE INDEX idx_candle_lookup ON raw.candle USING btree (secid, interval_name, candle_time DESC);


--
-- Name: idx_news_match_instrument; Type: INDEX; Schema: raw; Owner: n8n_user
--

CREATE INDEX idx_news_match_instrument ON raw.news_instrument_match USING btree (instrument_id, matched_at DESC);


--
-- Name: idx_news_published_at; Type: INDEX; Schema: raw; Owner: n8n_user
--

CREATE INDEX idx_news_published_at ON raw.news_item USING btree (published_at DESC);


--
-- Name: idx_news_source; Type: INDEX; Schema: raw; Owner: n8n_user
--

CREATE INDEX idx_news_source ON raw.news_item USING btree (source);


--
-- Name: idx_instrument_active; Type: INDEX; Schema: ref; Owner: n8n_user
--

CREATE INDEX idx_instrument_active ON ref.instrument USING btree (active);


--
-- Name: idx_instrument_group; Type: INDEX; Schema: ref; Owner: n8n_user
--

CREATE INDEX idx_instrument_group ON ref.instrument USING btree (instrument_group);


--
-- Name: idx_orders_status; Type: INDEX; Schema: trading; Owner: n8n_user
--

CREATE INDEX idx_orders_status ON trading.orders USING btree (status);


--
-- Name: idx_orders_trader; Type: INDEX; Schema: trading; Owner: n8n_user
--

CREATE INDEX idx_orders_trader ON trading.orders USING btree (trader_name, status);


--
-- Name: news_instrument_match news_instrument_match_instrument_id_fkey; Type: FK CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.news_instrument_match
    ADD CONSTRAINT news_instrument_match_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES ref.instrument(instrument_id) ON DELETE CASCADE;


--
-- Name: news_instrument_match news_instrument_match_news_id_fkey; Type: FK CONSTRAINT; Schema: raw; Owner: n8n_user
--

ALTER TABLE ONLY raw.news_instrument_match
    ADD CONSTRAINT news_instrument_match_news_id_fkey FOREIGN KEY (news_id) REFERENCES raw.news_item(news_id) ON DELETE CASCADE;


--
-- Name: SCHEMA analytics; Type: ACL; Schema: -; Owner: market_owner
--

GRANT USAGE ON SCHEMA analytics TO market_rw;
GRANT USAGE ON SCHEMA analytics TO market_ro;


--
-- Name: SCHEMA ingest; Type: ACL; Schema: -; Owner: market_owner
--

GRANT USAGE ON SCHEMA ingest TO market_rw;
GRANT USAGE ON SCHEMA ingest TO market_ro;


--
-- Name: SCHEMA meta; Type: ACL; Schema: -; Owner: market_owner
--

GRANT USAGE ON SCHEMA meta TO market_rw;
GRANT USAGE ON SCHEMA meta TO market_ro;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;


--
-- Name: SCHEMA raw; Type: ACL; Schema: -; Owner: market_owner
--

GRANT USAGE ON SCHEMA raw TO market_rw;
GRANT USAGE ON SCHEMA raw TO market_ro;


--
-- Name: SCHEMA ref; Type: ACL; Schema: -; Owner: market_owner
--

GRANT USAGE ON SCHEMA ref TO market_rw;
GRANT USAGE ON SCHEMA ref TO market_ro;


--
-- Name: TABLE instrument_snapshot; Type: ACL; Schema: analytics; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE analytics.instrument_snapshot TO market_rw;
GRANT SELECT ON TABLE analytics.instrument_snapshot TO market_ro;


--
-- Name: SEQUENCE instrument_snapshot_snapshot_id_seq; Type: ACL; Schema: analytics; Owner: n8n_user
--

GRANT ALL ON SEQUENCE analytics.instrument_snapshot_snapshot_id_seq TO market_rw;
GRANT SELECT ON SEQUENCE analytics.instrument_snapshot_snapshot_id_seq TO market_ro;


--
-- Name: TABLE latest_snapshot; Type: ACL; Schema: analytics; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE analytics.latest_snapshot TO market_rw;
GRANT SELECT ON TABLE analytics.latest_snapshot TO market_ro;


--
-- Name: TABLE research_digest; Type: ACL; Schema: analytics; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE analytics.research_digest TO market_rw;
GRANT SELECT ON TABLE analytics.research_digest TO market_ro;


--
-- Name: SEQUENCE research_digest_digest_id_seq; Type: ACL; Schema: analytics; Owner: n8n_user
--

GRANT ALL ON SEQUENCE analytics.research_digest_digest_id_seq TO market_rw;
GRANT SELECT ON SEQUENCE analytics.research_digest_digest_id_seq TO market_ro;


--
-- Name: TABLE instrument; Type: ACL; Schema: ref; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE ref.instrument TO market_rw;
GRANT SELECT ON TABLE ref.instrument TO market_ro;


--
-- Name: TABLE lightrag_document_log; Type: ACL; Schema: ingest; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE ingest.lightrag_document_log TO market_rw;
GRANT SELECT ON TABLE ingest.lightrag_document_log TO market_ro;


--
-- Name: SEQUENCE lightrag_document_log_document_log_id_seq; Type: ACL; Schema: ingest; Owner: n8n_user
--

GRANT ALL ON SEQUENCE ingest.lightrag_document_log_document_log_id_seq TO market_rw;
GRANT SELECT ON SEQUENCE ingest.lightrag_document_log_document_log_id_seq TO market_ro;


--
-- Name: TABLE workflow_cursor; Type: ACL; Schema: meta; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE meta.workflow_cursor TO market_rw;
GRANT SELECT ON TABLE meta.workflow_cursor TO market_ro;


--
-- Name: TABLE candle; Type: ACL; Schema: raw; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE raw.candle TO market_rw;
GRANT SELECT ON TABLE raw.candle TO market_ro;


--
-- Name: TABLE news_instrument_match; Type: ACL; Schema: raw; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE raw.news_instrument_match TO market_rw;
GRANT SELECT ON TABLE raw.news_instrument_match TO market_ro;


--
-- Name: TABLE news_item; Type: ACL; Schema: raw; Owner: n8n_user
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE raw.news_item TO market_rw;
GRANT SELECT ON TABLE raw.news_item TO market_ro;


--
-- Name: SEQUENCE news_item_news_id_seq; Type: ACL; Schema: raw; Owner: n8n_user
--

GRANT ALL ON SEQUENCE raw.news_item_news_id_seq TO market_rw;
GRANT SELECT ON SEQUENCE raw.news_item_news_id_seq TO market_ro;


--
-- Name: SEQUENCE instrument_instrument_id_seq; Type: ACL; Schema: ref; Owner: n8n_user
--

GRANT ALL ON SEQUENCE ref.instrument_instrument_id_seq TO market_rw;
GRANT SELECT ON SEQUENCE ref.instrument_instrument_id_seq TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: analytics; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA analytics GRANT ALL ON SEQUENCES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA analytics GRANT SELECT ON SEQUENCES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: analytics; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA analytics GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA analytics GRANT SELECT ON TABLES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: ingest; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ingest GRANT ALL ON SEQUENCES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ingest GRANT SELECT ON SEQUENCES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: ingest; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ingest GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ingest GRANT SELECT ON TABLES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: meta; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA meta GRANT ALL ON SEQUENCES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA meta GRANT SELECT ON SEQUENCES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: meta; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA meta GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA meta GRANT SELECT ON TABLES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: raw; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA raw GRANT ALL ON SEQUENCES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA raw GRANT SELECT ON SEQUENCES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: raw; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA raw GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA raw GRANT SELECT ON TABLES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: ref; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ref GRANT ALL ON SEQUENCES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ref GRANT SELECT ON SEQUENCES TO market_ro;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: ref; Owner: market_owner
--

ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ref GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO market_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE market_owner IN SCHEMA ref GRANT SELECT ON TABLES TO market_ro;


--
-- PostgreSQL database dump complete
--

\unrestrict V6PodoaVNyDLRDdRhd0XzqKa1hlIRrartiVExUKTROfrTWafIYrXmUQp0ZdjPAN

