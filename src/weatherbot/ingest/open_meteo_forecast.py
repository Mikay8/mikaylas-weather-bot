"""Pull next-day forecast highs from Open-Meteo for NYC Central Park and
store them in `forecasts` as second/third independent forecast sources
alongside NWS.

Two variants share this module:
  - OPEN_METEO: Open-Meteo's auto-blended forecast (GFS + other models,
    whichever it judges best-resolution for this location)
  - ECMWF: Open-Meteo's dedicated /v1/ecmwf endpoint, ECMWF IFS HRES only -
    the single model with the best independent verified accuracy (WMO
    anomaly correlation scores) of any public global model. Same free,
    no-key, non-commercial terms as the blended endpoint.

Both disagreeing sharply with NWS on the same target_date is a real signal
that the forecast is unusually uncertain that day, not just model noise.
See weatherbot/api/forecast_agreement.py for how these are compared.
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
    "ECMWF": "https://api.open-meteo.com/v1/ecmwf",
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
    if model_source not in SOURCES:
        raise ValueError(f"Unknown model_source: {model_source} (expected one of {list(SOURCES)})")

    now = datetime.now(timezone.utc)
    # NYC-local, not UTC: UTC is 4-5 hours ahead of Eastern, so a bare UTC
    # `now` flips to the next date while it's still evening in NYC, which
    # would then be matched against the wrong day in the API's response
    # (its `daily.time` values are already NYC-local - see the timezone
    # param in fetch_daily_forecast).
    target_date = (now.astimezone(EASTERN) + timedelta(days=1)).date()

    log_source = "ecmwf" if model_source == "ECMWF" else "open_meteo"
    with httpx.Client(timeout=30.0, event_hooks=make_logged_hooks(log_source)) as client:
        raw_response = fetch_daily_forecast(client, SOURCES[model_source])

    predicted_high = extract_high_for_date(raw_response, target_date)
    if predicted_high is None:
        print(f"[{now.isoformat()}] No {model_source} maxTemperature value found for {target_date}.")
        return

    store_forecast(model_source, target_date, predicted_high, raw_response, now)
    print(
        f"[{now.isoformat()}] Stored {model_source} forecast: "
        f"target_date={target_date} predicted_high={predicted_high}F"
    )


if __name__ == "__main__":
    run("OPEN_METEO")
