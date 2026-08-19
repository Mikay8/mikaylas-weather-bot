-- Auto-trading bot: tags which trades the bot placed vs. a human, and stores
-- the bot's on/off state plus its tunable parameters in one settings row
-- (single-row table, same pattern as paper_wallet) so they're editable from
-- the Settings page without a redeploy.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS is_bot_trade BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS bot_settings (
    id SERIAL PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    bet_amount NUMERIC NOT NULL DEFAULT 25,
    edge_threshold NUMERIC NOT NULL DEFAULT 0.03,      -- fee-adjusted edge required to trade
    skip_if_position_exists BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO bot_settings (enabled, bet_amount, edge_threshold, skip_if_position_exists)
SELECT FALSE, 25, 0.03, TRUE
WHERE NOT EXISTS (SELECT 1 FROM bot_settings);
