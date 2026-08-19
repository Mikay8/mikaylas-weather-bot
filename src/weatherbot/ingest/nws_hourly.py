"""Live hourly weather for the Today card: current conditions (from the
KNYC/Central Park observation station - our exact settlement station),
plus past and future hourly temperatures. This is presentational only -
nothing here is stored, unlike forecasts/settlements/market_snapshots -
so it's fetched fresh on request rather than ingested on a schedule.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

LAT, LON = 40.7789, -73.9692  # Central Park, NYC
STATION_ID = "KNYC"
NWS_BASE = "https://api.weather.gov"


def _user_agent() -> str:
    contact = os.environ.get("NWS_USER_AGENT_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("NWS_USER_AGENT_CONTACT must be set in .env")
    return f"(mikaylas-weather-bot, {contact})"


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _user_agent()}, timeout=15.0)


def celsius_to_fahrenheit(c: float) -> float:
    return c * 9 / 5 + 32


def fetch_current(client: httpx.Client) -> dict | None:
    resp = client.get(f"{NWS_BASE}/stations/{STATION_ID}/observations/latest")
    resp.raise_for_status()
    props = resp.json()["properties"]
    temp_c = props["temperature"]["value"]
    if temp_c is None:
        return None
    return {
        "timestamp": props["timestamp"],
        "temperature": round(celsius_to_fahrenheit(temp_c), 1),
        "condition": props.get("textDescription"),
    }


def fetch_past_hourly(client: httpx.Client, hours: int = 12) -> list[dict]:
    resp = client.get(
        f"{NWS_BASE}/stations/{STATION_ID}/observations", params={"limit": hours}
    )
    resp.raise_for_status()
    out = []
    for feature in resp.json()["features"]:
        p = feature["properties"]
        temp_c = p["temperature"]["value"]
        if temp_c is None:
            continue
        out.append(
            {
                "timestamp": p["timestamp"],
                "temperature": round(celsius_to_fahrenheit(temp_c), 1),
                "condition": p.get("textDescription"),
            }
        )
    out.reverse()  # API returns newest-first; we want chronological
    return out


def fetch_future_hourly(client: httpx.Client, hours: int = 12) -> list[dict]:
    points_resp = client.get(f"{NWS_BASE}/points/{LAT},{LON}")
    points_resp.raise_for_status()
    grid_id = points_resp.json()["properties"]["gridId"]
    grid_x = points_resp.json()["properties"]["gridX"]
    grid_y = points_resp.json()["properties"]["gridY"]

    resp = client.get(f"{NWS_BASE}/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly")
    resp.raise_for_status()
    periods = resp.json()["properties"]["periods"][:hours]
    return [
        {
            "timestamp": p["startTime"],
            "temperature": float(p["temperature"]),
            "condition": p.get("shortForecast"),
        }
        for p in periods
    ]


def get_hourly_view(past_hours: int = 12, future_hours: int = 36) -> dict:
    with _client() as client:
        current = fetch_current(client)
        past = fetch_past_hourly(client, past_hours)
        future = fetch_future_hourly(client, future_hours)
    return {"current": current, "past": past, "future": future}
