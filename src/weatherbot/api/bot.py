"""Auto-trading bot: evaluates open recommendations and places a paper bet
whenever fee-adjusted edge crosses the configured threshold, skipping any
market where a position (bot or human) already exists for that day if
skip_if_position_exists is on. All bot settings live in bot_settings (a
single-row table, same pattern as paper_wallet) so they're editable from
the Settings page without a redeploy.

Runs on its own schedule (bot-cron) independent of the dashboard - see
.railway/railway.ts. Every trade this places is tagged is_bot_trade=TRUE so
the UI can show "Bot" vs "You" without ambiguity.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from weatherbot.api.recommendations import build_recommendations
from weatherbot.api.trading import BetError, execute_bet
from weatherbot.db import get_session

router = APIRouter(prefix="/api/bot")


def _get_settings(session) -> dict:
    row = session.execute(
        text(
            """
            SELECT enabled, bet_amount, edge_threshold, skip_if_position_exists, updated_at
            FROM bot_settings
            LIMIT 1
            """
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Bot settings not initialized")
    return dict(row._mapping)


@router.get("/settings")
def get_bot_settings():
    session = get_session()
    try:
        return _get_settings(session)
    finally:
        session.close()


class BotSettingsUpdate(BaseModel):
    enabled: bool | None = None
    bet_amount: float | None = None
    edge_threshold: float | None = None
    skip_if_position_exists: bool | None = None


@router.post("/settings")
def update_bot_settings(req: BotSettingsUpdate):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "bet_amount" in fields and fields["bet_amount"] <= 0:
        raise HTTPException(status_code=422, detail="bet_amount must be positive")
    if "edge_threshold" in fields and not (0 <= fields["edge_threshold"] <= 1):
        raise HTTPException(status_code=422, detail="edge_threshold must be between 0 and 1")

    session = get_session()
    try:
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        session.execute(
            text(f"UPDATE bot_settings SET {set_clause}, updated_at = now()"),
            fields,
        )
        session.commit()
        return _get_settings(session)
    finally:
        session.close()


def run_bot_cycle() -> dict:
    """Evaluate current recommendations and place paper trades for any that
    clear the configured edge threshold. Returns a summary for logging."""
    session = get_session()
    try:
        settings = _get_settings(session)
        if not settings["enabled"]:
            return {"skipped": "bot disabled", "trades_placed": 0}

        threshold = float(settings["edge_threshold"])
        amount = float(settings["bet_amount"])
        skip_if_position_exists = settings["skip_if_position_exists"]

        existing_dates: set[str] = set()
        if skip_if_position_exists:
            rows = session.execute(
                text("SELECT DISTINCT target_date FROM trades WHERE status = 'open'")
            ).fetchall()
            existing_dates = {str(r.target_date) for r in rows if r.target_date is not None}

        recs = build_recommendations()
        placed = []
        skipped = []

        for rec in recs:
            target_date = str(rec["target_date"])
            fee_adjusted_edge = rec["fee_adjusted_edge"]

            if fee_adjusted_edge is None or fee_adjusted_edge < threshold:
                continue
            if skip_if_position_exists and target_date in existing_dates:
                skipped.append({"contract_id": rec["contract_id"], "reason": "position exists"})
                continue

            try:
                result = execute_bet(
                    session, rec["contract_id"], rec["side"], amount, is_bot_trade=True
                )
                placed.append(result)
                existing_dates.add(target_date)  # don't double-place within this cycle
            except BetError as e:
                skipped.append({"contract_id": rec["contract_id"], "reason": str(e)})

        return {
            "trades_placed": len(placed),
            "placed": placed,
            "skipped": skipped,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        session.close()


@router.post("/run")
def trigger_bot_cycle():
    """Manually trigger one bot evaluation cycle (also used by bot-cron)."""
    return run_bot_cycle()


if __name__ == "__main__":
    import json

    print(json.dumps(run_bot_cycle(), indent=2, default=str))
