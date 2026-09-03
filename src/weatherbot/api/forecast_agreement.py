"""Compares NWS (the model's actual input - see recommendations.py) against
every other independent forecast source for the same target_date. A sharp
disagreement means the forecast is unusually uncertain that day - the
probability model only ever sees NWS's point forecast, so it has no way to
know this on its own. Surfaced on the dashboard and used to pause the
auto-trading bot for that day.
"""

from datetime import date

from sqlalchemy import text

from weatherbot.db import get_session

# Chosen from typical NWS-vs-actual MAE (~2.2F, see /api/calibration) - a
# same-day gap between two independent sources bigger than this is well
# outside normal forecast noise, not just the two methods rounding differently.
DISAGREEMENT_THRESHOLD_F = 4.0

# Every source besides NWS that's compared against it. Add a new ingest
# module's model_source here to fold it into the agreement check - no other
# code changes needed. ECMWF was dropped 2026-09 to cut down on cron/source
# count - Open-Meteo alone is still an independent check against NWS.
SECONDARY_SOURCES = ["OPEN_METEO"]


def get_forecast_agreement(target_date: date) -> dict | None:
    """Latest NWS prediction vs. every secondary source's latest prediction
    for target_date. Returns None if NWS or none of the secondary sources
    have reported yet."""
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (model_source) model_source, predicted_high, forecast_time
                FROM forecasts
                WHERE target_date = :target_date
                  AND model_source IN :sources
                ORDER BY model_source, forecast_time DESC
                """
            ),
            {"target_date": target_date, "sources": tuple(["NWS", *SECONDARY_SOURCES])},
        ).fetchall()
    finally:
        session.close()

    by_source = {r.model_source: r for r in rows}
    nws = by_source.get("NWS")
    if nws is None:
        return None

    nws_high = float(nws.predicted_high)
    comparisons = {}
    for source in SECONDARY_SOURCES:
        row = by_source.get(source)
        if row is None:
            continue
        high = float(row.predicted_high)
        comparisons[source] = {
            "predicted_high": high,
            "spread": round(abs(nws_high - high), 1),
        }

    if not comparisons:
        return None

    disagrees = any(c["spread"] >= DISAGREEMENT_THRESHOLD_F for c in comparisons.values())
    worst = max(comparisons.values(), key=lambda c: c["spread"])

    return {
        "target_date": target_date,
        "nws_predicted_high": nws_high,
        "sources": comparisons,
        "spread": worst["spread"],
        "disagrees": disagrees,
    }
