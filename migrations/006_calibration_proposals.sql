-- Durable log of calibration_proposer.py runs, so the Analytics dashboard
-- tab can show PR history without re-hitting GitHub live and without
-- re-running the pattern check itself. One row per run, whether or not it
-- actually opened a PR - most rows will have pr_url NULL (threshold not
-- met, no coherent pattern, or backtest didn't confirm improvement) since
-- that's the expected common case, not an error.

CREATE TABLE IF NOT EXISTS calibration_proposals (
    id SERIAL PRIMARY KEY,
    outcome TEXT NOT NULL,          -- 'pr_opened' | 'threshold_not_met' | 'no_pattern' | 'backtest_rejected'
    reasoning TEXT,                 -- Claude's pattern reasoning, when it ran that far
    old_factor NUMERIC,
    new_factor NUMERIC,
    pr_url TEXT,
    diagnosis_ids INTEGER[],        -- trade_diagnoses.id rows considered for this run
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_calibration_proposals_created_at ON calibration_proposals (created_at DESC);
