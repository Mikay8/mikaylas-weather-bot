-- Cross-market relative-value scanner (see src/weatherbot/cross_market.py).
-- One row per matched Kalshi<->Polymarket event pair, plus an append-only
-- snapshot per scan so the UI can show how the price gap and the net
-- (fee-adjusted, executable bid/ask) arbitrage edge evolve over time.
-- Manifold columns are an indicative play-money reference only.
-- The scanner also runs this DDL idempotently at store time, so applying
-- this migration by hand is belt-and-braces, not a prerequisite.

CREATE TABLE IF NOT EXISTS cross_market_pairs (
    id SERIAL PRIMARY KEY,
    kalshi_ticker TEXT NOT NULL,
    kalshi_event_ticker TEXT,
    kalshi_title TEXT NOT NULL,
    poly_condition_id TEXT NOT NULL,
    poly_slug TEXT,
    poly_question TEXT NOT NULL,
    manifold_id TEXT,
    manifold_question TEXT,
    match_score DOUBLE PRECISION NOT NULL,
    close_time TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kalshi_ticker, poly_condition_id)
);

CREATE TABLE IF NOT EXISTS cross_market_snapshots (
    id SERIAL PRIMARY KEY,
    pair_id INTEGER NOT NULL REFERENCES cross_market_pairs(id) ON DELETE CASCADE,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kalshi_yes_bid DOUBLE PRECISION,
    kalshi_yes_ask DOUBLE PRECISION,
    poly_yes_bid DOUBLE PRECISION,
    poly_yes_ask DOUBLE PRECISION,
    manifold_prob DOUBLE PRECISION,
    mid_gap DOUBLE PRECISION,
    arb_edge DOUBLE PRECISION,
    arb_direction TEXT,
    kalshi_volume DOUBLE PRECISION,
    poly_volume DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_xm_snapshots_pair_time
    ON cross_market_snapshots (pair_id, scanned_at DESC);
