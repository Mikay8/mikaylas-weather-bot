# Mikayla's Weather Bot — Build Prompt for Claude Code

## Project Overview

Build a systematic trading bot that predicts New York City daily high-temperature outcomes and trades Kalshi's KXHIGHNY contracts when the model's calibrated probability diverges meaningfully from the market's implied price. The bot should start in a fully paper-trading / simulation mode — no real orders should be placed until explicitly enabled.

This is a data pipeline + statistical modeling + execution project, not an LLM project. Do not use an LLM for the core prediction — use forecast data, ensemble spread, and calibration statistics.

---

## Setup Instructions (do this first)

Connect Claude Code to the Railway MCP so it can provision and manage the Postgres database and deployment directly:

```
claude mcp add railway --transport http https://mcp.railway.com
```

Use this MCP connection to:
- Provision a Postgres database on Railway
- Store the connection string as a Railway environment variable (never hardcode credentials)
- Set up a service to run the Python scripts on a schedule

Also connect Claude Code to the GitHub MCP so it can create a repo, commit, and manage version control directly:

```
claude mcp add --transport http github https://api.githubcopilot.com/mcp/ --header "Authorization: Bearer YOUR_GITHUB_PAT"
```

Notes:
- You'll need a GitHub Personal Access Token (fine-grained, scoped to the repos you want Claude to work with) — generate one from GitHub's token settings and substitute it for `YOUR_GITHUB_PAT`.
- `claude mcp add` saves this config without validating the token, so double-check the connection works (e.g. ask Claude Code to list your repos) before relying on it.
- GitHub's MCP tooling has been changing recently — if this command errors out, check Claude Code's current docs (`https://code.claude.com/docs/en/mcp`) for the latest syntax, since some setups have shifted toward using the `gh` CLI directly instead.
- Use this connection to create a private repo for this project, commit early and often (especially before/after each build phase below), and keep API keys and the Railway DB connection string out of version control via `.gitignore` / environment variables.

---

## Scope for v1

- **City**: New York only (NWS settlement station: Central Park)
- **Contract type**: Kalshi KXHIGHNY (daily high temperature) only — no precipitation, no other cities, no low-temperature contracts yet
- **Horizon**: next-day forecasts only (not same-day, not multi-day-out)
- **Mode**: paper trading only until explicitly told to enable live orders

---

## Tech Stack

- **Language**: Python 3.11+
- **Database**: PostgreSQL, hosted on Railway (via the Railway MCP connection above)
- **HTTP/API clients**: `httpx` or `requests` for REST; `websockets` for Kalshi's live market data feed if available
- **Data analysis**: `pandas`, `numpy`, `scipy` (for probability distribution math)
- **Modeling/calibration**: `scikit-learn` and/or `statsmodels`
- **Scheduling**: `APScheduler` or Railway's built-in cron/scheduled jobs
- **ORM/DB access**: `sqlalchemy` (works cleanly with Postgres and makes any future migration easier)
- **Config/secrets**: environment variables via Railway, loaded with `python-dotenv` for local dev
- **Alerting**: simple Telegram bot or email notification for trade confirmations and any kill-switch triggers (build this after the core pipeline works)

Do NOT use: LLMs for prediction, Kubernetes, message queues (Kafka etc.), heavy orchestration tools (Airflow). Keep this lean — it does not need that scale.

---

## Data Sources

1. **NWS/NOAA forecast data**: `api.weather.gov` (free, no API key required) — pull point forecasts for the NYC Central Park station area.
2. **Settlement source of truth**: NWS official daily climate report for Central Park — this is what Kalshi settles against. Confirm the exact station/report format before building the backtest.
3. **Market data**: Kalshi's public API (REST for snapshots, websocket for live bid/ask if available) for KXHIGHNY contracts — prices, volume, open interest, bracket structure.
4. **Historical data**: pull as much backfilled history as both APIs allow for backtesting. Note: for forecasts, try to get data "as it existed at the time" rather than reanalyzed data, to avoid lookahead bias in the backtest.

---

## Database Schema (starting point — adjust as needed)

```sql
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    station TEXT NOT NULL DEFAULT 'NYC_CENTRAL_PARK',
    forecast_time TIMESTAMP NOT NULL,       -- when this forecast was pulled
    target_date DATE NOT NULL,               -- date being forecasted
    predicted_high NUMERIC,
    confidence_low NUMERIC,                  -- lower bound of forecast range/spread
    confidence_high NUMERIC,                 -- upper bound
    model_source TEXT,                       -- e.g. 'NWS', 'GFS', 'ECMWF'
    raw_response JSONB                       -- store full API response for later reprocessing
);

CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,               -- Kalshi contract ticker
    timestamp TIMESTAMP NOT NULL,
    bracket_low NUMERIC,
    bracket_high NUMERIC,
    yes_bid NUMERIC,
    yes_ask NUMERIC,
    implied_prob NUMERIC,
    volume NUMERIC,
    open_interest NUMERIC
);

CREATE TABLE settlements (
    id SERIAL PRIMARY KEY,
    station TEXT NOT NULL DEFAULT 'NYC_CENTRAL_PARK',
    date DATE NOT NULL UNIQUE,
    actual_high NUMERIC NOT NULL,
    source TEXT                              -- confirm this matches Kalshi's settlement source exactly
);

CREATE TABLE model_predictions (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    target_date DATE NOT NULL,
    model_prob NUMERIC NOT NULL,
    market_prob NUMERIC NOT NULL,
    edge NUMERIC NOT NULL,                   -- model_prob - market_prob
    fee_adjusted_edge NUMERIC
);

CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    contract_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    side TEXT NOT NULL,                      -- 'yes' or 'no'
    price NUMERIC NOT NULL,
    size NUMERIC NOT NULL,
    model_prob_at_trade NUMERIC,
    is_paper_trade BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT,                             -- 'open', 'settled_win', 'settled_loss'
    pnl NUMERIC
);
```

---

## Build Phases (build and validate in this order — do not skip ahead)

### Phase 1: Data pipeline
- Write scripts to pull NWS forecast data for NYC and store in `forecasts`.
- Write scripts to pull Kalshi KXHIGHNY market data and store in `market_snapshots`.
- Write a script to backfill/pull historical settlement data into `settlements`.
- Set up scheduling so forecast and market data are pulled at regular intervals (forecasts a few times a day aligned with model runs; market data more frequently, ideally via websocket for live prices).
- Validate: confirm data is landing correctly in Postgres, spot-check a few records against the raw API responses.

### Phase 2: Backtesting
- Using historical forecast + settlement + market price data, build a backtest script.
- Convert historical forecasts into a probability distribution across Kalshi's bracket structure (start with a normal or skew-normal distribution around the predicted high, using the forecast's stated confidence/spread).
- Compare model-implied probability vs. historical market price at various lead times.
- Calculate what a trading strategy would have earned/lost after Kalshi's fees (roughly 3-7% of net winnings — confirm exact current fee structure from Kalshi's docs).
- Report results broken out by lead time (how far before settlement) and by season if enough data exists.
- Do NOT proceed to Phase 3 until backtest shows a plausible, fee-adjusted positive edge with a reasonable sample size.

### Phase 3: Calibration model
- Build a calibration layer (logistic regression or gradient boosting) that learns how well raw forecast probabilities have historically matched actual outcomes at this specific station, and corrects for systematic bias (e.g., over/under-confidence).
- Re-run the backtest using calibrated probabilities and compare to the naive version from Phase 2.

### Phase 4: Paper trading
- Build a live pipeline that pulls current forecasts and market prices, computes model probability, compares to market, and logs a "paper trade" (in `trades` with `is_paper_trade = TRUE`) whenever the edge exceeds a defined threshold — do not place real orders.
- Run for at least a few weeks and log everything: predictions, market prices, hypothetical trades, and outcomes once settlements come in.
- Build a simple report/dashboard (can be a script that outputs a summary, doesn't need to be fancy) comparing live paper-trading performance to backtest expectations.

### Phase 5: Risk management and live execution (build but keep disabled by default)
- Implement position sizing logic (fractional Kelly or a fixed small % of bankroll).
- Implement hard daily/weekly loss limits that halt trading automatically.
- Implement a kill switch — one command/flag to immediately stop all new order placement.
- Implement real order placement via Kalshi's API, gated behind an explicit config flag (e.g. `LIVE_TRADING_ENABLED=false` by default) — this must default to off and require a deliberate, explicit change to turn on.
- Add alerting (Telegram or email) for trade confirmations and any kill-switch triggers.

### Phase 6: Go-live (only after Phase 4 paper results are consistent with backtest expectations)
- Enable live trading with small position sizes first.
- Continue logging everything and comparing live results to backtest/paper expectations on an ongoing basis.
- Define in advance what "this isn't working" looks like (e.g., N weeks of underperformance vs. backtest, or a max drawdown threshold) and build the halt logic to enforce it automatically if possible.

---

## Important Guardrails

- Never hardcode API keys or database credentials — use environment variables via Railway.
- Default to paper trading; live trading must be an explicit, deliberate opt-in.
- Log every prediction and every trade from day one, even in paper mode — this data is essential for validating the model over time.
- Watch for lookahead bias in backtesting — only use data that would have actually been available at each point in time.
- Confirm the exact Kalshi settlement source/station and fee structure directly from Kalshi's current API docs before finalizing the backtest, since these details matter a lot and may have changed.

---

## First Deliverable

Start with Phase 1 only: set up the Railway Postgres database (via the Railway MCP), create the schema above, and build working scripts that pull and store NWS forecast data and Kalshi KXHIGHNY market data for New York. Confirm data is landing correctly before moving to backtesting.
