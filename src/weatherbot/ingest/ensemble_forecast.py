"""Averages NWS, Open-Meteo, and ECMWF into one blended forecast — a lower-
variance point estimate than any single source, the same idea consumer
weather apps use when they blend models.

Stored as its own model_source='ENSEMBLE' row in `forecasts` (a plain TEXT
column, so this needs no schema change) rather than computed ad-hoc at read
time, so it plugs into calibration.py/load_paired_history() and the
recommendation engine for free — both already take an arbitrary
model_source string.

Doesn't require all three sources to be present: forecast-cron,
open-meteo-cron, and ecmwf-cron run on the same schedule but aren't
guaranteed-ordered (see .railway/railway.ts), so this averages whichever
of the three have already reported for the target date.
"""

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session
from weatherbot.ingest import nws_hourly, open_meteo_forecast

STATION = "NYC_CENTRAL_PARK"
SOURCES = ("NWS", "OPEN_METEO", "ECMWF")
EASTERN = ZoneInfo("America/New_York")


def _hour_key(timestamp: str) -> str:
    """Normalizes NWS's offset-aware hourly timestamps ('...T12:00:00-04:00')
    and Open-Meteo's naive local ones ('...T12:00') to the same join key -
    both already represent NYC-local hours, just formatted differently."""
    return timestamp[:13]  # "YYYY-MM-DDTHH"


def get_ensemble_hourly_view(past_hours: int = 12, future_hours: int = 36) -> dict:
    """current/past stay NWS-only - they're observed station readings, not
    forecasts, so there's no second source to average them against. Only
    future (an actual forecast) is blended across sources."""
    with nws_hourly._client() as client:
        current = nws_hourly.fetch_current(client)
        past = nws_hourly.fetch_past_hourly(client, past_hours)
        nws_future = nws_hourly.fetch_future_hourly(client, future_hours)

    by_hour: dict[str, list[float]] = {}
    condition_by_hour: dict[str, str | None] = {}
    for p in nws_future:
        key = _hour_key(p["timestamp"])
        by_hour.setdefault(key, []).append(p["temperature"])
        condition_by_hour[key] = p["condition"]

    for model_source in ("OPEN_METEO", "ECMWF"):
        base_url = open_meteo_forecast.SOURCES[model_source]
        log_source = "ecmwf" if model_source == "ECMWF" else "open_meteo"
        try:
            with httpx.Client(timeout=30.0, event_hooks=make_logged_hooks(log_source)) as client:
                points = open_meteo_forecast.fetch_hourly_forecast(client, base_url, future_hours)
        except httpx.HTTPError:
            continue  # ensemble degrades gracefully to whichever sources responded
        for p in points:
            by_hour.setdefault(_hour_key(p["timestamp"]), []).append(p["temperature"])

    future = []
    for nws_p in nws_future:
        key = _hour_key(nws_p["timestamp"])
        temps = by_hour[key]
        future.append(
            {
                "timestamp": nws_p["timestamp"],
                "temperature": round(sum(temps) / len(temps), 1),
                "condition": condition_by_hour.get(key),
            }
        )

    return {"current": current, "past": past, "future": future}


def _latest_daily_highs(session, target_date: date) -> dict[str, float]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (model_source) model_source, predicted_high
            FROM forecasts
            WHERE target_date = :target_date AND model_source IN :sources
            ORDER BY model_source, forecast_time DESC
            """
        ),
        {"target_date": target_date, "sources": SOURCES},
    ).fetchall()
    return {r.model_source: float(r.predicted_high) for r in rows if r.predicted_high is not None}


def store_ensemble_forecast(target_date: date, highs: dict[str, float], forecast_time: datetime):
    mean_high = round(sum(highs.values()) / len(highs), 1)
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO forecasts
                    (station, forecast_time, target_date, predicted_high,
                     confidence_low, confidence_high, model_source, raw_response)
                VALUES
                    (:station, :forecast_time, :target_date, :predicted_high,
                     :confidence_low, :confidence_high, 'ENSEMBLE', :raw_response)
                ON CONFLICT (station, forecast_time, target_date, model_source) DO NOTHING
                """
            ),
            {
                "station": STATION,
                "forecast_time": forecast_time,
                "target_date": target_date,
                "predicted_high": mean_high,
                "confidence_low": min(highs.values()),
                "confidence_high": max(highs.values()),
                "raw_response": json.dumps({"sources": highs, "mean": mean_high}),
            },
        )
        session.commit()
    finally:
        session.close()
    return mean_high


def run() -> None:
    """Computes the ensemble for both today and tomorrow - today's is needed
    for a same-day 6am trade (see bot-cron); tomorrow's is the original
    evening-before-trade case."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(EASTERN).date()
    tomorrow = today + timedelta(days=1)

    session = get_session()
    try:
        for target_date in (today, tomorrow):
            highs = _latest_daily_highs(session, target_date)
            if not highs:
                print(f"[{now.isoformat()}] No source forecasts yet for {target_date}, skipping ensemble.")
                continue
            mean_high = store_ensemble_forecast(target_date, highs, now)
            print(
                f"[{now.isoformat()}] Stored ENSEMBLE forecast: target_date={target_date} "
                f"predicted_high={mean_high}F (from {sorted(highs)})"
            )
    finally:
        session.close()


if __name__ == "__main__":
    run()
