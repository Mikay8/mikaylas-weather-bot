"""Phase 2 recommendation engine: scores currently open KXHIGHNY markets by
comparing the calibrated model probability (model.py, fit on GFS_MOS history)
against the market's current implied probability, fee-adjusted.

Real historical Kalshi prices don't exist yet to backtest P&L against (see
calibration.py's docstring), so this only ever looks at *live* open markets —
it's the forward-looking half of Phase 2, not a historical strategy backtest.
Every recommendation is also logged to `model_predictions` so it accumulates
its own track record over time.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from weatherbot.api.settle import kalshi_fee
from weatherbot.backtest.calibration import load_paired_history
from weatherbot.backtest.model import bracket_probability, fit_error_stats
from weatherbot.db import get_session

MIN_EDGE_THRESHOLD = 0.03  # fee-adjusted edge below this isn't worth surfacing


def _latest_predicted_high(session, target_date) -> float | None:
    row = session.execute(
        text(
            """
            SELECT predicted_high FROM forecasts
            WHERE target_date = :target_date
            ORDER BY forecast_time DESC
            LIMIT 1
            """
        ),
        {"target_date": target_date},
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def build_recommendations() -> list[dict]:
    errors = [e for _, p, a in load_paired_history() for e in [a - p]]
    if len(errors) < 2:
        return []
    stats = fit_error_stats(errors)

    session = get_session()
    try:
        markets = session.execute(
            text(
                """
                SELECT DISTINCT ON (ms.contract_id)
                    ms.contract_id, ms.target_date, ms.bracket_low, ms.bracket_high,
                    ms.strike_type, ms.yes_bid, ms.yes_ask, ms.implied_prob,
                    ms.volume, ms.open_interest
                FROM market_snapshots ms
                LEFT JOIN settlements s ON s.date = ms.target_date
                WHERE s.date IS NULL
                ORDER BY ms.contract_id, ms.timestamp DESC
                """
            )
        ).fetchall()

        recs = []
        now = datetime.now(timezone.utc)
        for m in markets:
            if m.target_date is None or m.strike_type is None or m.implied_prob is None:
                continue
            predicted_high = _latest_predicted_high(session, m.target_date)
            if predicted_high is None:
                continue

            model_prob = bracket_probability(
                predicted_high,
                stats,
                m.strike_type,
                float(m.bracket_low) if m.bracket_low is not None else None,
                float(m.bracket_high) if m.bracket_high is not None else None,
            )
            market_prob = float(m.implied_prob)
            edge_yes = model_prob - market_prob
            edge_no = (1 - model_prob) - (1 - market_prob)

            if edge_yes >= edge_no:
                side, edge, price = "yes", edge_yes, m.yes_ask
            else:
                side, edge, price = "no", edge_no, (
                    Decimal("1") - m.yes_bid if m.yes_bid is not None else None
                )

            fee_adjusted_edge = None
            if price is not None and 0 < price < 1:
                fee = kalshi_fee(Decimal("1"), Decimal(str(price)))
                fee_adjusted_edge = edge - float(fee)

            session.execute(
                text(
                    """
                    INSERT INTO model_predictions
                        (contract_id, timestamp, target_date, model_prob, market_prob,
                         edge, fee_adjusted_edge)
                    VALUES
                        (:contract_id, :timestamp, :target_date, :model_prob, :market_prob,
                         :edge, :fee_adjusted_edge)
                    """
                ),
                {
                    "contract_id": m.contract_id,
                    "timestamp": now,
                    "target_date": m.target_date,
                    "model_prob": model_prob,
                    "market_prob": market_prob,
                    "edge": edge,
                    "fee_adjusted_edge": fee_adjusted_edge,
                },
            )

            recs.append(
                {
                    "contract_id": m.contract_id,
                    "target_date": m.target_date,
                    "bracket_low": m.bracket_low,
                    "bracket_high": m.bracket_high,
                    "strike_type": m.strike_type,
                    "predicted_high": predicted_high,
                    "model_prob": round(model_prob, 4),
                    "market_prob": round(market_prob, 4),
                    "side": side,
                    "edge": round(edge, 4),
                    "fee_adjusted_edge": round(fee_adjusted_edge, 4)
                    if fee_adjusted_edge is not None
                    else None,
                    "recommend": fee_adjusted_edge is not None
                    and fee_adjusted_edge >= MIN_EDGE_THRESHOLD,
                    "volume": m.volume,
                    "open_interest": m.open_interest,
                }
            )

        session.commit()
        recs.sort(key=lambda r: r["fee_adjusted_edge"] or -1, reverse=True)
        return recs
    finally:
        session.close()
