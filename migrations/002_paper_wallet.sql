-- Manual paper-trading wallet: a single fake balance plus bet-resolution
-- fields on `trades` needed to settle a bracket bet against `settlements`
-- without re-deriving bracket bounds from the contract ticker string.

CREATE TABLE IF NOT EXISTS paper_wallet (
    id SERIAL PRIMARY KEY,
    balance NUMERIC NOT NULL,
    starting_balance NUMERIC NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO paper_wallet (balance, starting_balance)
SELECT 1000, 1000
WHERE NOT EXISTS (SELECT 1 FROM paper_wallet);

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS target_date DATE,
    ADD COLUMN IF NOT EXISTS bracket_low NUMERIC,
    ADD COLUMN IF NOT EXISTS bracket_high NUMERIC,
    ADD COLUMN IF NOT EXISTS strike_type TEXT,        -- 'greater' | 'less' | 'between'
    ADD COLUMN IF NOT EXISTS fee NUMERIC,
    ADD COLUMN IF NOT EXISTS station TEXT NOT NULL DEFAULT 'NYC_CENTRAL_PARK';

CREATE INDEX IF NOT EXISTS idx_trades_target_date ON trades (target_date);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);

ALTER TABLE market_snapshots
    ADD COLUMN IF NOT EXISTS target_date DATE,
    ADD COLUMN IF NOT EXISTS strike_type TEXT;         -- 'greater' | 'less' | 'between'

CREATE INDEX IF NOT EXISTS idx_market_snapshots_target_date ON market_snapshots (target_date);
