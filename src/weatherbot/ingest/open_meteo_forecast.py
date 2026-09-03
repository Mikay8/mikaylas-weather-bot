"""Pull next-day forecast highs from Open-Meteo for NYC Central Park and
store them in `forecasts` as a second independent forecast source alongside
NWS.

Used to also support an ECMWF variant (Open-Meteo's dedicated /v1/ecmwf
endpoint, ECMWF IFS HRES only) - dropped 2026-09 to cut down on cron/source
count, so this module is Open-Meteo-only now, though it's kept generic on
model_source in case another Open-Meteo-hosted model is worth adding later.

Disagreeing sharply with NWS on the same target_date is a real signal that
the forecast is unusually uncertain that day, not just model noise. See
weatherbot/api/forecast_agreement.py for how these are compared.
"""

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session

STATION = "NYC_CENTRAL_PARK"
LAT, LON = 40.7789, -73.9692  # Central Park, NYC
EASTERN = ZoneInfo("America/New_York")

SOURCES = {
    "OPEN_METEO": "https://api.open-meteo.com/v1/forecast",
}


def fetch_daily_forecast(client: httpx.Client, base_url: str) -> dict:
    resp = client.get(
        base_url,
        params={
            "latitude": LAT,
            "longitude": LON,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": "America/New_York",
            "forecast_days": 3,
        },
    )
    resp.raise_for_status()
    return resp.json()


def fetch_hourly_forecast(client: httpx.Client, base_url: str, hours: int = 36) -> list[dict]:
    """Same endpoint as fetch_daily_forecast supports an hourly block in the
    same request - no separate call needed. Returns points shaped like
    nws_hourly.py's HourlyPoint (timestamp, temperature, condition) so they
    can be averaged against NWS's hourly forecast point-for-point."""
    resp = client.get(
        base_url,
        params={
            "latitude": LAT,
            "longitude": LON,
            "hourly": "temperature_2m",
            "temperature_unit": "fahrenheit",
            "timezone": "America/New_York",
            "forecast_days": 2,
        },
    )
    resp.raise_for_status()
    data = resp.json()["hourly"]
    return [
        {"timestamp": t, "temperature": round(float(temp), 1), "condition": None}
        for t, temp in zip(data["time"], data["temperature_2m"])
        if temp is not None
    ][:hours]


def extract_high_for_date(raw_response: dict, target_date: date) -> float | None:
    target_str = target_date.isoformat()
    for d, high in zip(raw_response["daily"]["time"], raw_response["daily"]["temperature_2m_max"]):
        if d == target_str:
            return round(float(high), 1) if high is not None else None
    return None


def store_forecast(
    model_source: str, target_date: date, predicted_high: float, raw_response: dict, forecast_time: datetime
):
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO forecasts
                    (station, forecast_time, target_date, predicted_high, model_source, raw_response)
                VALUES
                    (:station, :forecast_time, :target_date, :predicted_high, :model_source, :raw_response)
                ON CONFLICT (station, forecast_time, target_date, model_source) DO NOTHING
                """
            ),
            {
                "station": STATION,
                "forecast_time": forecast_time,
                "target_date": target_date,
                "predicted_high": predicted_high,
                "model_source": model_source,
                "raw_response": json.dumps(raw_response),
            },
        )
        session.commit()
    finally:
        session.close()


def run(model_source: str = "OPEN_METEO") -> None:
    """Stores both today's and tomorrow's predicted high from a single daily
    pull (forecast_days=3 already covers both). Today's is needed for a
    same-day 6am trade (see bot-cron); tomorrow's is the original
    evening-before-trade case."""
    if model_source not in SOURCES:
        raise ValueError(f"Unknown model_source: {model_source} (expected one of {list(SOURCES)})")

    now = datetime.now(timezone.utc)
    # NYC-local, not UTC: UTC is 4-5 hours ahead of Eastern, so a bare UTC
    # `now` flips to the next date while it's still evening in NYC, which
    # would then be matched against the wrong day in the API's response
    # (its `daily.time` values are already NYC-local - see the timezone
    # param in fetch_daily_forecast).
    today = now.astimezone(EASTERN).date()
    tomorrow = today + timedelta(days=1)

    with httpx.Client(timeout=30.0, event_hooks=make_logged_hooks("open_meteo")) as client:
        raw_response = fetch_daily_forecast(client, SOURCES[model_source])

    for target_date in (today, tomorrow):
        predicted_high = extract_high_for_date(raw_response, target_date)
        if predicted_high is None:
            print(f"[{now.isoformat()}] No {model_source} maxTemperature value found for {target_date}.")
            continue
        store_forecast(model_source, target_date, predicted_high, raw_response, now)
        print(
            f"[{now.isoformat()}] Stored {model_source} forecast: "
            f"target_date={target_date} predicted_high={predicted_high}F"
        )


if __name__ == "__main__":
    run("OPEN_METEO")
