"""Nightly Claude analyst: diagnoses every newly-settled trade against its
forecast/market/settlement context and logs a structured note to
trade_diagnoses (see migrations/005_trade_diagnoses.sql).

This is diagnosis only - it never touches model.py, bot_settings, or any
trading parameter directly. A human reads the accumulated diagnoses (or the
pattern-triggered PR from propose_calibration_change, once enough
systematic_bias diagnoses stack up) and decides whether to act on them via
the existing calibration.py / pnl_backtest.py walk-forward backtest. See the
build spec discussion this module came out of for why: a single trade's
outcome is mostly noise, and letting an LLM's plausible-sounding narrative
silently rewrite calibration would trade honest uncertainty for confident
miscalibration.

Run after settlement-cron (which resolves trades and populates
`settlements`) - see analyst-cron in .railway/railway.ts.
"""

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

import anthropic
from pydantic import BaseModel
from sqlalchemy import text

from weatherbot.db import get_session

MODEL = "claude-opus-5"


def _client() -> anthropic.Anthropic:
    # Identity-linked API keys (tied to a personal Console login spanning
    # multiple workspaces, as opposed to a plain workspace-scoped key)
    # require this header on every request - the SDK doesn't infer it from
    # an env var on its own. ANTHROPIC_WORKSPACE_ID is optional: unset it
    # entirely if/when this switches to a workspace-scoped key.
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(default_headers=headers)


class TradeDiagnosis(BaseModel):
    category: Literal["bad_luck", "systematic_bias", "data_bug", "other"]
    confidence: Literal["low", "medium", "high"]
    summary: str


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def load_undiagnosed_settled_trades(session) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT t.id AS trade_id, t.side, t.price, t.size, t.strike_type,
                   t.bracket_low, t.bracket_high, t.fee, t.pnl, t.status,
                   t.target_date, t.station, t.is_bot_trade,
                   s.actual_high,
                   f.predicted_high, f.model_source, f.forecast_time
            FROM trades t
            JOIN settlements s
              ON s.date = t.target_date AND s.station = t.station
            LEFT JOIN trade_diagnoses td ON td.trade_id = t.id
            LEFT JOIN LATERAL (
                SELECT predicted_high, model_source, forecast_time
                FROM forecasts
                WHERE target_date = t.target_date AND model_source = 'GFS_MOS'
                ORDER BY forecast_time DESC
                LIMIT 1
            ) f ON TRUE
            WHERE t.status IN ('settled_win', 'settled_loss')
              AND td.id IS NULL
            ORDER BY t.target_date
            """
        )
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def diagnose_trade(client: anthropic.Anthropic, trade: dict) -> TradeDiagnosis:
    context = json.dumps(trade, indent=2, default=_json_default)
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        output_config={"effort": "medium"},
        system=(
            "You are a post-mortem analyst for a systematic weather-trading bot "
            "(NYC daily high temperature, Kalshi KXHIGHNY contracts). The bot's "
            "probability model is Normal(predicted_high + bias, stdev) fit via "
            "walk-forward seasonal calibration on GFS_MOS forecast error history. "
            "Given one settled trade's forecast, market, and outcome data, classify "
            "why it won or lost:\n"
            "- bad_luck: the model's stated probability was reasonable and this is "
            "consistent with normal variance around a well-calibrated distribution "
            "(a low-probability outcome will still happen sometimes)\n"
            "- systematic_bias: the forecast error or trade outcome fits a pattern "
            "that suggests a persistent, correctable model issue (e.g. a directional "
            "bias in a particular season or synoptic pattern, underdispersion), not "
            "one-off noise\n"
            "- data_bug: something about the input data looks wrong or inconsistent "
            "(implausible forecast/settlement values, stale data, missing fields)\n"
            "- other: doesn't fit the above\n"
            "You only ever see one trade at a time - do not claim high confidence in "
            "systematic_bias from a single data point; that requires a pattern across "
            "many trades, which a separate step aggregates. Keep summary to 2-3 "
            "sentences."
        ),
        messages=[{"role": "user", "content": f"Trade to diagnose:\n{context}"}],
        output_format=TradeDiagnosis,
    )
    return response.parsed_output


def save_diagnosis(session, trade_id: int, diagnosis: TradeDiagnosis) -> None:
    session.execute(
        text(
            """
            INSERT INTO trade_diagnoses (trade_id, category, confidence, summary, raw_response, model)
            VALUES (:trade_id, :category, :confidence, :summary, :raw_response, :model)
            ON CONFLICT (trade_id) DO NOTHING
            """
        ),
        {
            "trade_id": trade_id,
            "category": diagnosis.category,
            "confidence": diagnosis.confidence,
            "summary": diagnosis.summary,
            "raw_response": json.dumps(diagnosis.model_dump()),
            "model": MODEL,
        },
    )


def run() -> dict:
    client = _client()
    session = get_session()
    diagnosed = []
    errors = []
    try:
        trades = load_undiagnosed_settled_trades(session)
        for trade in trades:
            try:
                diagnosis = diagnose_trade(client, trade)
                save_diagnosis(session, trade["trade_id"], diagnosis)
                session.commit()
                diagnosed.append({"trade_id": trade["trade_id"], "category": diagnosis.category})
            except Exception as e:  # noqa: BLE001 - log and continue to the next trade
                session.rollback()
                errors.append({"trade_id": trade["trade_id"], "error": str(e)})

        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "n_trades_considered": len(trades),
            "diagnosed": diagnosed,
            "errors": errors,
        }
    finally:
        session.close()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
