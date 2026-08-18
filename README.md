# Mikayla's Weather Bot

Systematic trading bot that predicts New York City daily high-temperature outcomes and trades Kalshi's `KXHIGHNY` contracts when calibrated model probability diverges from market price.

Paper-trading only until `LIVE_TRADING_ENABLED=true` is explicitly set. See [mikaylas-weather-bot-prompt.md](mikaylas-weather-bot-prompt.md) for the full build spec.

## Status

Phase 1 (data pipeline) — in progress.

## Local setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env  # fill in DATABASE_URL, Kalshi keys, etc.
```

### Connecting to the Railway Postgres DB locally

The DB has no public network access (by design — it holds trading data).
To connect from your laptop, open a private SSH tunnel in one terminal:

```bash
railway connect postgres --tunnel-only --port 15432
```

Then set `DATABASE_URL` in `.env` to the URL it prints (`127.0.0.1:15432`).
Leave the tunnel running while you run scripts/migrations locally.

### Running the Phase 1 ingest scripts

```bash
python3 -m weatherbot.ingest.nws_forecast     # pulls next-day NYC forecast
python3 -m weatherbot.ingest.kalshi_market    # pulls open KXHIGHNY market snapshots
python3 -m weatherbot.ingest.nws_settlement   # backfills recent settlement highs
```

### Settlement source caveat

Kalshi's KXHIGHNY contracts settle "according to The Weather Company" per
their live market rules text — not the NWS CLI report the Kalshi Help
Center docs describe. The Weather Company has no free public API for
historical Central Park highs, so `settlements` uses the NWS CLI report
(same station, CLINYC) as a proxy. Revisit before Phase 4 if backtesting
shows the two sources diverge meaningfully near bracket edges.

## Scope (v1)

- City: New York (NWS Central Park station) only
- Contract: Kalshi `KXHIGHNY` (daily high temp) only
- Horizon: next-day forecasts only
- Mode: paper trading only until explicitly enabled
