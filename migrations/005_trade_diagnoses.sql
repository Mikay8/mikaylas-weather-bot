-- Nightly Claude analyst: diagnoses each newly-settled trade (won or lost)
-- against its forecast/market/settlement context, so misses accumulate a
-- reviewable trail instead of just a pnl number. See
-- weatherbot/analysis/trade_analyst.py. Append-only, same spirit as
-- api_call_logs - a diagnostic aid, not something the bot reads back to
-- change its own behavior (that stays human-gated via calibration.py +
-- pnl_backtest.py, triggered manually off a pattern found here).

CREATE TABLE IF NOT EXISTS trade_diagnoses (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES trades (id),
    category TEXT NOT NULL,        -- 'bad_luck' | 'systematic_bias' | 'data_bug' | 'other'
    confidence TEXT NOT NULL,      -- 'low' | 'medium' | 'high'
    summary TEXT NOT NULL,         -- one-paragraph rationale from Claude
    raw_response JSONB NOT NULL,   -- full structured output, for audit
    model TEXT NOT NULL,           -- e.g. 'claude-opus-5'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_diagnoses_trade_id ON trade_diagnoses (trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_diagnoses_created_at ON trade_diagnoses (created_at DESC);
