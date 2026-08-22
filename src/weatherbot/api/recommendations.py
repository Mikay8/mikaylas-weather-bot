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
from zoneinfo import ZoneInfo

from sqlalchemy import text

from weatherbot.api.forecast_agreement import SECONDARY_SOURCES
from weatherbot.api.settle import kalshi_fee
from weatherbot.backtest.calibration import load_paired_history
from weatherbot.backtest.model import bracket_probability, fit_error_stats_seasonal
from weatherbot.db import get_session

MIN_EDGE_THRESHOLD = 0.03  # fee-adjusted edge below this isn't worth surfacing
EASTERN = ZoneInfo("America/New_York")


def is_forecast_stale(forecast_time: datetime, target_date) -> bool:
    """True if `forecast_time` predates the current NYC calendar day while
    `target_date` is today or already past - i.e. a same-day trade is about
    to use a forecast pulled on a previous day, when a fresher same-day pull
    should exist (forecast-cron runs at 2am/7am/1pm/6pm NYC). A next-day
    target_date (the normal case: trading tomorrow's market this evening)
    is never considered stale by this check - an evening-before pull is
    exactly the expected input there."""
    today_nyc = datetime.now(EASTERN).date()
    if target_date > today_nyc:
        return False
    return forecast_time.astimezone(EASTERN).date() < today_nyc


def _latest_predicted_high(session, target_date) -> tuple[float, datetime] | None:
    # Prefer the ENSEMBLE row (mean of NWS/Open-Meteo/ECMWF, written by
    # ensemble_forecast.py) as the model's point-forecast input - a
    # lower-variance estimate than any single source. The model's
    # bias/stdev correction (fit_error_stats_seasonal, via
    # load_paired_history) is still fit on GFS_MOS history only: Open-Meteo
    # and ECMWF don't yet have enough paired forecast/actual history to
    # refit against an ensemble-specific error distribution (as of this
    # writing, a few days vs. GFS_MOS's full year). Applying GFS_MOS stats
    # to the ensemble mean is the same "apply GFS_MOS stats to whichever
    # forecast is freshest" approach this model used pre-ensemble, just
    # with a better point estimate - not a fully-refit ensemble model.
    # Revisit once /api/calibration?model_source=ENSEMBLE has ~30+ days.
    row = session.execute(
        text(
            """
            SELECT predicted_high, forecast_time FROM forecasts
            WHERE target_date = :target_date AND model_source = 'ENSEMBLE'
            ORDER BY forecast_time DESC
            LIMIT 1
            """
        ),
        {"target_date": target_date},
    ).fetchone()
    if row and row[0] is not None:
        return float(row[0]), row[1]

    # Fallback for a target_date ensemble-cron hasn't reached yet (e.g. a
    # brand-new day before any of the source crons have landed): same
    # NWS-only logic as before the ensemble existed. Excludes every
    # SECONDARY_SOURCES entry plus ENSEMBLE itself so a stray future
    # ENSEMBLE row can never be picked up here as an "other source."
    row = session.execute(
        text(
            """
            SELECT predicted_high, forecast_time FROM forecasts
            WHERE target_date = :target_date AND model_source NOT IN :excluded
            ORDER BY forecast_time DESC
            LIMIT 1
            """
        ),
        {"target_date": target_date, "excluded": tuple([*SECONDARY_SOURCES, "ENSEMBLE"])},
    ).fetchone()
    return (float(row[0]), row[1]) if row and row[0] is not None else None


def build_recommendations() -> list[dict]:
    # Deliberately still GFS_MOS (the default) rather than ENSEMBLE - see
    # the comment in _latest_predicted_high. The point-forecast input is
    # the ensemble mean, but the error correction applied to it is still
    # fit on single-source history until ensemble history is deep enough.
    dated_errors = [(d, a - p) for d, p, a in load_paired_history()]
    if len(dated_errors) < 2:
        return []

    session = get_session()
    try:
        markets = session.execute(
            text(
                """
                SELECT DISTINCT ON (ms.contract_id)
                    ms.contract_id, ms.target_date, ms.bracket_low, ms.bracket_high,
                    ms.strike_type, ms.yes_bid, ms.yes_ask, ms.implied_prob,
                    ms.volume, ms.open_interest,
                    ms.raw_response ->> 'yes_sub_title' AS kalshi_label
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
            forecast_lookup = _latest_predicted_high(session, m.target_date)
            if forecast_lookup is None:
                continue
            predicted_high, forecast_time = forecast_lookup
            stale = is_forecast_stale(forecast_time, m.target_date)

            stats = fit_error_stats_seasonal(dated_errors, m.target_date)
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
                    "kalshi_label": m.kalshi_label,
                    "predicted_high": predicted_high,
                    "forecast_time": forecast_time,
                    "forecast_stale": stale,
                    "model_prob": round(model_prob, 4),
                    "market_prob": round(market_prob, 4),
                    "side": side,
                    "edge": round(edge, 4),
                    "fee_adjusted_edge": round(fee_adjusted_edge, 4)
                    if fee_adjusted_edge is not None
                    else None,
                    "recommend": fee_adjusted_edge is not None
                    and fee_adjusted_edge >= MIN_EDGE_THRESHOLD
                    and not stale,
                    "volume": m.volume,
                    "open_interest": m.open_interest,
                }
            )

        session.commit()
        recs.sort(key=lambda r: r["fee_adjusted_edge"] or -1, reverse=True)
        return recs
    finally:
        session.close()
