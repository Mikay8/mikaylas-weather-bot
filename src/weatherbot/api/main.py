import os
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from weatherbot.api.bot import router as bot_router
from weatherbot.api.forecast_agreement import get_forecast_agreement
from weatherbot.api.recommendations import build_recommendations
from weatherbot.api.settings import router as settings_router
from weatherbot.api.settle import resolve_pending_trades
from weatherbot.api.trading import BetError, execute_bet
from weatherbot.backtest.calibration import run as run_calibration
from weatherbot.db import get_session
from weatherbot.ingest.nws_hourly import get_hourly_view

EASTERN = ZoneInfo("America/New_York")

app = FastAPI(title="Mikayla's Weather Bot API")

_web_origins = [o.strip() for o in os.environ.get("WEB_PUBLIC_URL", "").split(",") if o.strip()]
_demo_origin_list = [o.strip() for o in os.environ.get("DEMO_PUBLIC_URL", "").split(",") if o.strip()]
_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    *_web_origins,
    *_demo_origin_list,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The demo deployment (view-only, no login) shares this API so it always
# reflects the same live data as the real dashboard. Its frontend hides all
# trade/settings controls, but that's just UI — this middleware is the actual
# enforcement, so a demo visitor can't drive mutations by calling the API
# directly (e.g. via devtools) even though it's paper money either way.
_demo_origins = set(_demo_origin_list)
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# GET-only exemptions under otherwise-blocked prefixes, if any get added later.
_READ_ONLY_EXEMPT_PATHS: set[str] = set()


@app.middleware("http")
async def block_demo_mutations(request: Request, call_next):
    if (
        _demo_origins
        and request.method in _MUTATING_METHODS
        and request.url.path not in _READ_ONLY_EXEMPT_PATHS
        and request.headers.get("origin") in _demo_origins
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "This is the read-only demo — trading and settings are disabled."},
        )
    return await call_next(request)


app.include_router(settings_router)
app.include_router(bot_router)


def _rows_to_dicts(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


@app.get("/api/status")
def data_freshness():
    """Last-pull timestamps for each data source, so the UI can show how
    stale the current view is (no automated scheduling exists yet — every
    pull so far has been triggered manually)."""
    session = get_session()
    try:
        last_forecast = session.execute(
            text("SELECT MAX(forecast_time) FROM forecasts")
        ).scalar()
        last_market = session.execute(
            text("SELECT MAX(timestamp) FROM market_snapshots")
        ).scalar()
        last_settlement = session.execute(
            text("SELECT MAX(date) FROM settlements")
        ).scalar()
        return {
            "last_forecast_pull": last_forecast,
            "last_market_pull": last_market,
            "last_settlement_date": last_settlement,
            "server_time": datetime.now(timezone.utc),
        }
    finally:
        session.close()


@app.get("/api/forecasts")
def list_forecasts(limit: int = 90):
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                SELECT id, station, forecast_time, target_date, predicted_high, model_source
                FROM forecasts
                ORDER BY target_date DESC, forecast_time DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return _rows_to_dicts(result)
    finally:
        session.close()


@app.get("/api/settlements")
def list_settlements(limit: int = 90):
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                SELECT id, station, date, actual_high, source
                FROM settlements
                ORDER BY date DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return _rows_to_dicts(result)
    finally:
        session.close()


@app.get("/api/forecast-vs-actual")
def forecast_vs_actual(limit: int = 90):
    """Join next-day forecasts against realized settlements for charting.

    Pivoted one row per target_date with predicted_high (NWS, the model's
    input — see recommendations.py) alongside a column per secondary
    source, rather than one row per model_source: with multiple forecast
    sources now populating `forecasts`, the old row-per-source join
    produced duplicate target_date rows once secondary sources started
    accumulating history."""
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                WITH latest_per_source AS (
                    SELECT DISTINCT ON (target_date, model_source)
                        target_date, model_source, predicted_high
                    FROM forecasts
                    ORDER BY target_date, model_source, forecast_time DESC
                ),
                dates AS (
                    SELECT DISTINCT target_date FROM latest_per_source
                    ORDER BY target_date DESC
                    LIMIT :limit
                )
                SELECT
                    d.target_date,
                    nws.predicted_high,
                    om.predicted_high AS open_meteo_predicted_high,
                    ecmwf.predicted_high AS ecmwf_predicted_high,
                    s.actual_high
                FROM dates d
                LEFT JOIN latest_per_source nws
                  ON nws.target_date = d.target_date AND nws.model_source = 'NWS'
                LEFT JOIN latest_per_source om
                  ON om.target_date = d.target_date AND om.model_source = 'OPEN_METEO'
                LEFT JOIN latest_per_source ecmwf
                  ON ecmwf.target_date = d.target_date AND ecmwf.model_source = 'ECMWF'
                LEFT JOIN settlements s
                  ON s.date = d.target_date AND s.station = 'NYC_CENTRAL_PARK'
                ORDER BY d.target_date DESC
                """
            ),
            {"limit": limit},
        )
        return _rows_to_dicts(result)
    finally:
        session.close()


@app.get("/api/markets")
def list_current_markets():
    """Latest snapshot per contract_id (most recent timestamp)."""
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                SELECT DISTINCT ON (contract_id)
                    contract_id, timestamp, target_date, bracket_low, bracket_high,
                    strike_type, yes_bid, yes_ask, implied_prob, volume, open_interest,
                    raw_response ->> 'yes_sub_title' AS kalshi_label,
                    raw_response ->> 'close_time' AS close_time
                FROM market_snapshots
                ORDER BY contract_id, timestamp DESC
                """
            )
        )
        return _rows_to_dicts(result)
    finally:
        session.close()


@app.get("/api/markets/{contract_id}/history")
def market_history(contract_id: str, limit: int = 200):
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                SELECT timestamp, yes_bid, yes_ask, implied_prob, volume, open_interest
                FROM market_snapshots
                WHERE contract_id = :contract_id
                ORDER BY timestamp DESC
                LIMIT :limit
                """
            ),
            {"contract_id": contract_id, "limit": limit},
        )
        return _rows_to_dicts(result)
    finally:
        session.close()


@app.get("/api/recommendations")
def get_recommendations():
    """Model probability vs. current market price for every open KXHIGHNY
    market, fee-adjusted. Forward-looking only — see recommendations.py."""
    return build_recommendations()


@app.get("/api/forecast-agreement")
def get_forecast_agreement_endpoint(target_date: date | None = None):
    """NWS vs. every secondary forecast source's predicted high for
    target_date (defaults to tomorrow, the bot's actual decision date) —
    see forecast_agreement.py."""
    if target_date is None:
        # NYC-local, not UTC - see the same fix in nws_forecast.py /
        # open_meteo_forecast.py for why a bare UTC `now` flips to the
        # next date hours before it's actually tomorrow in NYC.
        target_date = (datetime.now(EASTERN) + timedelta(days=1)).date()
    result = get_forecast_agreement(target_date)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No forecast pair yet for {target_date}"
        )
    return result


_hourly_cache: dict = {"data": None, "fetched_at": 0.0}
_HOURLY_CACHE_TTL_SECONDS = 300  # NWS station observations update ~hourly anyway


@app.get("/api/weather/hourly")
def get_hourly_weather():
    """Current conditions + past/future hourly temps for the Today card,
    live from NWS (KNYC/Central Park) — not stored, so cached briefly in
    memory to avoid re-fetching on every dashboard poll."""
    now = time.monotonic()
    if _hourly_cache["data"] is not None and now - _hourly_cache["fetched_at"] < _HOURLY_CACHE_TTL_SECONDS:
        return _hourly_cache["data"]
    try:
        data = get_hourly_view()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch hourly weather: {e}")
    _hourly_cache["data"] = data
    _hourly_cache["fetched_at"] = now
    return data


@app.get("/api/calibration")
def get_calibration(model_source: str = "GFS_MOS", min_train_days: int = 30):
    """Walk-forward calibration backtest of the probability model against
    real settlements (no lookahead). See calibration.py."""
    try:
        return run_calibration(model_source=model_source, min_train_days=min_train_days)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/wallet")
def get_wallet():
    session = get_session()
    try:
        wallet = session.execute(
            text("SELECT balance, starting_balance, updated_at FROM paper_wallet LIMIT 1")
        ).fetchone()
        if wallet is None:
            raise HTTPException(status_code=404, detail="Wallet not initialized")

        open_trades = _rows_to_dicts(
            session.execute(
                text(
                    """
                    SELECT id, contract_id, timestamp, side, price, size, target_date,
                           bracket_low, bracket_high, strike_type, fee, is_bot_trade
                    FROM trades
                    WHERE status = 'open' AND is_paper_trade = TRUE
                    ORDER BY timestamp DESC
                    """
                )
            )
        )
        settled_trades = _rows_to_dicts(
            session.execute(
                text(
                    """
                    SELECT id, contract_id, timestamp, side, price, size, target_date,
                           bracket_low, bracket_high, strike_type, fee, status, pnl, is_bot_trade
                    FROM trades
                    WHERE status IN ('settled_win', 'settled_loss') AND is_paper_trade = TRUE
                    ORDER BY timestamp DESC
                    LIMIT 200
                    """
                )
            )
        )
        realized_pnl = sum((t["pnl"] or 0) for t in settled_trades)

        return {
            "balance": wallet.balance,
            "starting_balance": wallet.starting_balance,
            "updated_at": wallet.updated_at,
            "realized_pnl": realized_pnl,
            "open_trades": open_trades,
            "settled_trades": settled_trades,
        }
    finally:
        session.close()


class PlaceBetRequest(BaseModel):
    contract_id: str
    side: str  # 'yes' or 'no'
    amount: float  # dollars to spend


@app.post("/api/wallet/bet")
def place_bet(req: PlaceBetRequest):
    session = get_session()
    try:
        try:
            return execute_bet(session, req.contract_id, req.side, req.amount, is_bot_trade=False)
        except BetError as e:
            msg = str(e)
            status_code = 404 if msg == "Market not found" else 422
            raise HTTPException(status_code=status_code, detail=msg)
    finally:
        session.close()


@app.post("/api/wallet/resolve")
def resolve_trades():
    count = resolve_pending_trades()
    return {"resolved": count}


@app.post("/api/wallet/reset")
def reset_wallet(starting_balance: float = 1000):
    session = get_session()
    try:
        session.execute(text("DELETE FROM trades WHERE is_paper_trade = TRUE"))
        session.execute(
            text(
                "UPDATE paper_wallet SET balance = :b, starting_balance = :b, updated_at = now()"
            ),
            {"b": starting_balance},
        )
        session.commit()
        return {"balance": starting_balance}
    finally:
        session.close()
