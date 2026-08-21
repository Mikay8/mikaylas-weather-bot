"""Pull NWS gridpoint forecast data for NYC Central Park and store next-day
predicted high in `forecasts`.

api.weather.gov's raw forecast (forecastGridData) gives a deterministic
maxTemperature series per day, no confidence interval. We store what's
available now; confidence_low/confidence_high stay NULL until Phase 2/3
derives them empirically from historical forecast error by lead time.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

from weatherbot.db import get_session
from sqlalchemy import text

load_dotenv()

STATION = "NYC_CENTRAL_PARK"
LAT, LON = 40.7789, -73.9692  # Central Park, NYC
NWS_BASE = "https://api.weather.gov"
EASTERN = ZoneInfo("America/New_York")


def _user_agent() -> str:
    contact = os.environ.get("NWS_USER_AGENT_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("NWS_USER_AGENT_CONTACT must be set in .env")
    return f"(mikaylas-weather-bot, {contact})"


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _user_agent()}, timeout=30.0)


def get_gridpoint(client: httpx.Client) -> tuple[str, int, int]:
    resp = client.get(f"{NWS_BASE}/points/{LAT},{LON}")
    resp.raise_for_status()
    props = resp.json()["properties"]
    return props["gridId"], props["gridX"], props["gridY"]


def fetch_grid_forecast(client: httpx.Client, grid_id: str, grid_x: int, grid_y: int) -> dict:
    resp = client.get(f"{NWS_BASE}/gridpoints/{grid_id}/{grid_x},{grid_y}")
    resp.raise_for_status()
    return resp.json()


def celsius_to_fahrenheit(c: float) -> float:
    return c * 9 / 5 + 32


def extract_next_day_high(grid_data: dict, now: datetime) -> tuple[datetime.date, float] | None:
    """Return (target_date, predicted_high_f) for the next calendar day's max temp.

    "Next day" is relative to NYC-local calendar day, not UTC - UTC is 4-5
    hours ahead of Eastern, so a bare UTC `now` flips to the next date while
    it's still evening in NYC (e.g. 8pm EDT is already midnight UTC),
    silently shifting every forecast a day early for hours at a stretch.
    """
    target_date = (now.astimezone(EASTERN) + timedelta(days=1)).date()
    values = grid_data["properties"]["maxTemperature"]["values"]
    for entry in values:
        valid_start = datetime.fromisoformat(entry["validTime"].split("/")[0])
        if valid_start.date() == target_date:
            uom = grid_data["properties"]["maxTemperature"]["uom"]
            value = entry["value"]
            if value is None:
                return None
            if "degC" in uom:
                value = celsius_to_fahrenheit(value)
            return target_date, round(value, 1)
    return None


def store_forecast(target_date, predicted_high: float, raw_response: dict, forecast_time: datetime):
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
                "model_source": "NWS",
                "raw_response": json.dumps(raw_response),
            },
        )
        session.commit()
    finally:
        session.close()


def run() -> None:
    now = datetime.now(timezone.utc)
    with _client() as client:
        grid_id, grid_x, grid_y = get_gridpoint(client)
        grid_data = fetch_grid_forecast(client, grid_id, grid_x, grid_y)

    result = extract_next_day_high(grid_data, now)
    if result is None:
        print(f"[{now.isoformat()}] No next-day maxTemperature value found in grid data.")
        return

    target_date, predicted_high = result
    store_forecast(target_date, predicted_high, grid_data, now)
    print(f"[{now.isoformat()}] Stored forecast: target_date={target_date} predicted_high={predicted_high}F")


if __name__ == "__main__":
    run()
