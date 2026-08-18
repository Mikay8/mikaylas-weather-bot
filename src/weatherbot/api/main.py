from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from weatherbot.api.settle import kalshi_fee, resolve_pending_trades
from weatherbot.db import get_session

app = FastAPI(title="Mikayla's Weather Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local dev only; tighten before any public deploy
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    """Join next-day forecasts against realized settlements for charting."""
    session = get_session()
    try:
        result = session.execute(
            text(
                """
                SELECT f.target_date, f.predicted_high, s.actual_high
                FROM forecasts f
                LEFT JOIN settlements s
                  ON s.date = f.target_date AND s.station = f.station
                ORDER BY f.target_date DESC
                LIMIT :limit
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
                    strike_type, yes_bid, yes_ask, implied_prob, volume, open_interest
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
                           bracket_low, bracket_high, strike_type, fee
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
                           status, pnl
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
    if req.side not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="side must be 'yes' or 'no'")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    session = get_session()
    try:
        market = session.execute(
            text(
                """
                SELECT contract_id, target_date, bracket_low, bracket_high, strike_type,
                       yes_bid, yes_ask
                FROM market_snapshots
                WHERE contract_id = :contract_id
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ),
            {"contract_id": req.contract_id},
        ).fetchone()
        if market is None:
            raise HTTPException(status_code=404, detail="Market not found")
        if market.target_date is None:
            raise HTTPException(status_code=422, detail="Market has no resolvable target_date")

        # You pay the ask side: yes_ask to buy YES, (1 - yes_bid) i.e. no_ask to buy NO.
        if req.side == "yes":
            price = market.yes_ask
        else:
            price = Decimal("1") - market.yes_bid if market.yes_bid is not None else None
        if price is None or price <= 0 or price >= 1:
            raise HTTPException(status_code=422, detail="No valid price available for this side")

        amount = Decimal(str(req.amount))
        wallet = session.execute(text("SELECT balance FROM paper_wallet LIMIT 1")).fetchone()
        if wallet.balance < amount:
            raise HTTPException(status_code=422, detail="Insufficient paper balance")

        contracts = amount / price
        fee = kalshi_fee(contracts, price)

        now = datetime.now(timezone.utc)
        session.execute(
            text(
                """
                INSERT INTO trades
                    (contract_id, timestamp, side, price, size, is_paper_trade, status,
                     target_date, bracket_low, bracket_high, strike_type, fee)
                VALUES
                    (:contract_id, :timestamp, :side, :price, :size, TRUE, 'open',
                     :target_date, :bracket_low, :bracket_high, :strike_type, :fee)
                """
            ),
            {
                "contract_id": req.contract_id,
                "timestamp": now,
                "side": req.side,
                "price": price,
                "size": amount,
                "target_date": market.target_date,
                "bracket_low": market.bracket_low,
                "bracket_high": market.bracket_high,
                "strike_type": market.strike_type,
                "fee": fee,
            },
        )
        session.execute(
            text("UPDATE paper_wallet SET balance = balance - :amount, updated_at = now()"),
            {"amount": amount},
        )
        session.commit()
        return {
            "contract_id": req.contract_id,
            "side": req.side,
            "price": float(price),
            "contracts": float(contracts),
            "fee": float(fee),
            "amount_spent": float(amount),
        }
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
