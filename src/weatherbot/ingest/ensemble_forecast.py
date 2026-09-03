"""Blends NWS and Open-Meteo hourly forecasts for the dashboard's "Today
card" - a lower-variance point estimate than either source alone, the same
idea consumer weather apps use when they blend models.

This only powers get_ensemble_hourly_view (a live, not-stored blend of the
next ~36h for display). It used to also write a daily model_source='ENSEMBLE'
row to `forecasts` (via store_ensemble_forecast/run(), called by a now-removed
ensemble-cron) for the recommendation engine and calibration.py to consume,
and blended in ECMWF too - both dropped 2026-09 to cut down on cron/source
count. recommendations.py trades on GFS_MOS directly now, not an ensemble.
"""

import httpx

from weatherbot.api_logger import make_logged_hooks
from weatherbot.ingest import nws_hourly, open_meteo_forecast


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

    base_url = open_meteo_forecast.SOURCES["OPEN_METEO"]
    try:
        with httpx.Client(timeout=30.0, event_hooks=make_logged_hooks("open_meteo")) as client:
            points = open_meteo_forecast.fetch_hourly_forecast(client, base_url, future_hours)
    except httpx.HTTPError:
        points = []  # ensemble degrades gracefully to NWS-only if Open-Meteo is down
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
