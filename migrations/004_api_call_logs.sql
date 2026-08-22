-- Persisted log of outbound API calls (NWS, IEM Mesonet, ECMWF/Open-Meteo,
-- Kalshi) so the Settings page can show request/response history instead of
-- just the current-moment reachability check in source_health. Rows older
-- than 24h are trimmed on insert (see api_logger.py) since this is a
-- debugging aid, not an audit trail.

CREATE TABLE IF NOT EXISTS api_call_logs (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,              -- 'nws' | 'iem' | 'ecmwf' | 'open_meteo' | 'kalshi'
    method TEXT NOT NULL,
    url TEXT NOT NULL,
    request_body TEXT,
    status_code INTEGER,
    response_body TEXT,
    error TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_call_logs_created_at ON api_call_logs (created_at DESC);
