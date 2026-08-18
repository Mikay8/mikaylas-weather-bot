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
cp .env.example .env  # fill in DATABASE_URL, Kalshi keys, etc.
```

## Scope (v1)

- City: New York (NWS Central Park station) only
- Contract: Kalshi `KXHIGHNY` (daily high temp) only
- Horizon: next-day forecasts only
- Mode: paper trading only until explicitly enabled
