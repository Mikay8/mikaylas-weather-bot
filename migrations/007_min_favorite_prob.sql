-- Replaces the edge-threshold trading rule with a favorite/confidence-floor
-- rule: bet whichever side (YES/NO) the model rates more likely, only when
-- that probability clears this floor - see recommendations.py's
-- MIN_FAVORITE_PROB comment for the backtest behind this. The old
-- edge_threshold rule (bet whichever side has the bigger model_prob -
-- market_prob edge) backtested as a net loser across 324 real historical
-- markets; this one backtests profitably from ~0.70 up, peaking ~0.76-0.80.
--
-- Renamed in place (not a new column) so existing bot_settings rows keep
-- their row identity and updated_at history - this is a change in what the
-- number means, not an additional knob. 0.78 as the new default matches the
-- backtest's best total P&L; old rows' edge_threshold values (expressed as
-- a 0-1 fraction, same storage shape) are overwritten since a 0.03-scale
-- "edge" and a 0.78-scale "probability floor" aren't comparable numbers -
-- carrying the old value forward would silently make the bot trade on
-- almost everything.

ALTER TABLE bot_settings RENAME COLUMN edge_threshold TO min_favorite_prob;

ALTER TABLE bot_settings ALTER COLUMN min_favorite_prob SET DEFAULT 0.78;

UPDATE bot_settings SET min_favorite_prob = 0.78;
