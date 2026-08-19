"""Compares the two independent forecast sources (NWS, Open-Meteo) for the
same target_date. A sharp disagreement means the forecast is unusually
uncertain that day - the recommendation engine's probability model only
ever sees one source's point forecast (see recommendations.py), so it has
no way to know this on its own. Surfaced on the dashboard and used to pause
the auto-trading bot for that day.
"""

from datetime import date

from sqlalchemy import text

from weatherbot.db import get_session

# Chosen from typical NWS-vs-actual MAE (~2.2F, see /api/calibration) - a
# same-day gap between two independent sources bigger than this is well
# outside normal forecast noise, not just the two methods rounding differently.
DISAGREEMENT_THRESHOLD_F = 4.0


def get_forecast_agreement(target_date: date) -> dict | None:
    """Latest NWS vs. latest Open-Meteo prediction for target_date, or None
    if either source hasn't reported yet."""
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (model_source) model_source, predicted_high, forecast_time
                FROM forecasts
                WHERE target_date = :target_date AND model_source IN ('NWS', 'OPEN_METEO')
                ORDER BY model_source, forecast_time DESC
                """
            ),
            {"target_date": target_date},
        ).fetchall()
    finally:
        session.close()

    by_source = {r.model_source: r for r in rows}
    nws = by_source.get("NWS")
    open_meteo = by_source.get("OPEN_METEO")
    if nws is None or open_meteo is None:
        return None

    nws_high = float(nws.predicted_high)
    om_high = float(open_meteo.predicted_high)
    spread = abs(nws_high - om_high)

    return {
        "target_date": target_date,
        "nws_predicted_high": nws_high,
        "open_meteo_predicted_high": om_high,
        "spread": round(spread, 1),
        "disagrees": spread >= DISAGREEMENT_THRESHOLD_F,
    }
