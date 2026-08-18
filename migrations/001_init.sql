-- Phase 1 schema: forecasts, market snapshots, settlements.
-- model_predictions and trades are created here too since the doc's
-- starting schema defines them, but they stay unused until Phase 2+.

CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    station TEXT NOT NULL DEFAULT 'NYC_CENTRAL_PARK',
    forecast_time TIMESTAMPTZ NOT NULL,      -- when this forecast was pulled
    target_date DATE NOT NULL,               -- date being forecasted
    predicted_high NUMERIC,                  -- degrees F
    confidence_low NUMERIC,                  -- reserved for Phase 2/3; NULL for now
    confidence_high NUMERIC,
    model_source TEXT NOT NULL DEFAULT 'NWS',
    raw_response JSONB,
    UNIQUE (station, forecast_time, target_date, model_source)
);

CREATE INDEX IF NOT EXISTS idx_forecasts_target_date ON forecasts (target_date);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,               -- Kalshi market ticker
    timestamp TIMESTAMPTZ NOT NULL,
    bracket_low NUMERIC,
    bracket_high NUMERIC,
    yes_bid NUMERIC,
    yes_ask NUMERIC,
    implied_prob NUMERIC,
    volume NUMERIC,
    open_interest NUMERIC,
    raw_response JSONB,
    UNIQUE (contract_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_contract ON market_snapshots (contract_id);

CREATE TABLE IF NOT EXISTS settlements (
    id SERIAL PRIMARY KEY,
    station TEXT NOT NULL DEFAULT 'NYC_CENTRAL_PARK',
    date DATE NOT NULL UNIQUE,
    actual_high NUMERIC NOT NULL,
    source TEXT NOT NULL DEFAULT 'NWS_CLI_NYC',
    raw_product_text TEXT
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    target_date DATE NOT NULL,
    model_prob NUMERIC NOT NULL,
    market_prob NUMERIC NOT NULL,
    edge NUMERIC NOT NULL,
    fee_adjusted_edge NUMERIC
);

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL,                      -- 'yes' or 'no'
    price NUMERIC NOT NULL,
    size NUMERIC NOT NULL,
    model_prob_at_trade NUMERIC,
    is_paper_trade BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT,                             -- 'open', 'settled_win', 'settled_loss'
    pnl NUMERIC
);
