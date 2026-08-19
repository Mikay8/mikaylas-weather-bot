"""Pull Open-Meteo's next-day forecast high for NYC Central Park and store it
in `forecasts` under model_source='OPEN_METEO' - a second, independent
forecast source alongside NWS.

Open-Meteo blends multiple national weather models (GFS, ECMWF, HRRR, etc.)
into one forecast rather than serving a single source's output, so it
disagreeing sharply with NWS on the same target_date is a real signal that
the forecast is unusually uncertain that day, not just model noise. See
weatherbot/api/forecast_agreement.py for how the two are compared.

No API key needed - Open-Meteo's forecast API is free for non-commercial
use. https://open-meteo.com/en/docs
"""

import json
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from weatherbot.db import get_session

STATION = "NYC_CENTRAL_PARK"
LAT, LON = 40.7789, -73.9692  # Central Park, NYC
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


def fetch_daily_forecast(client: httpx.Client) -> dict:
    resp = client.get(
        OPEN_METEO_BASE,
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


def store_forecast(target_date: date, predicted_high: float, raw_response: dict, forecast_time: datetime):
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
                "model_source": "OPEN_METEO",
                "raw_response": json.dumps(raw_response),
            },
        )
        session.commit()
    finally:
        session.close()


def run() -> None:
    now = datetime.now(timezone.utc)
    target_date = (now + timedelta(days=1)).date()

    with httpx.Client(timeout=30.0) as client:
        raw_response = fetch_daily_forecast(client)

    predicted_high = extract_high_for_date(raw_response, target_date)
    if predicted_high is None:
        print(f"[{now.isoformat()}] No Open-Meteo maxTemperature value found for {target_date}.")
        return

    store_forecast(target_date, predicted_high, raw_response, now)
    print(f"[{now.isoformat()}] Stored Open-Meteo forecast: target_date={target_date} predicted_high={predicted_high}F")


if __name__ == "__main__":
    run()
