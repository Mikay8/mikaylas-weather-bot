"""Backfill historical next-day forecasts from IEM's MOS archive — free,
no key, station KNYC, GFS model, back to 2000+. Each row is tagged with
the exact `runtime` (when the forecast was issued), so no lookahead bias.

MOS ftime/n_x convention (verified against live data 2026-08-18):
the n_x value at a given `ftime` is the daytime max/min for the LOCAL
(US/Eastern) calendar date that ftime falls into once converted from
UTC — NOT the UTC calendar date of ftime itself. E.g. ftime=2026-08-19
00:00 UTC = 2026-08-18 20:00 EDT, so that n_x belongs to Aug 18, not
Aug 19. Getting this wrong silently shifts every forecast by a day.

v1 scope: next-day forecasts only. For a forecast issued at `runtime`,
we take the n_x value whose local target_date is exactly one day after
runtime's local date — i.e. the first true "next calendar day" daytime
high in the MOS output.
"""

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session

load_dotenv()

STATION = "NYC_CENTRAL_PARK"
IEM_STATION = "KNYC"
IEM_MODEL = "GFS"
IEM_BASE = "https://mesonet.agron.iastate.edu/api/1"
MODEL_SOURCE = "GFS_MOS"
EASTERN = ZoneInfo("America/New_York")


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, event_hooks=make_logged_hooks("iem"))


def fetch_mos_run(client: httpx.Client, runtime: datetime, retries: int = 3) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.get(
                f"{IEM_BASE}/mos.json",
                params={
                    "station": IEM_STATION,
                    "model": IEM_MODEL,
                    "runtime": runtime.strftime("%Y-%m-%d %H:%MZ"),
                },
            )
            if resp.status_code == 404:
                return []  # no MOS run archived for this date (gap in IEM's archive)
            resp.raise_for_status()
            return resp.json()["data"]
        except httpx.HTTPError as e:
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  warning: giving up on {runtime.date()} after {retries} retries ({last_error})")
    return []


def to_eastern_date(ftime_str: str) -> date:
    ftime_utc = datetime.strptime(ftime_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return ftime_utc.astimezone(EASTERN).date()


def extract_next_day_high(rows: list[dict], runtime: datetime) -> tuple[date, float] | None:
    runtime_local_date = runtime.astimezone(EASTERN).date()
    target_date = runtime_local_date + timedelta(days=1)
    for row in rows:
        if row.get("n_x") is None:
            continue
        row_date = to_eastern_date(row["ftime"])
        if row_date == target_date:
            return target_date, row["n_x"]
    return None


def store_forecast(target_date: date, predicted_high: float, runtime: datetime, raw_rows: list[dict]):
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
                "forecast_time": runtime,
                "target_date": target_date,
                "predicted_high": predicted_high,
                "model_source": MODEL_SOURCE,
                "raw_response": json.dumps(raw_rows),
            },
        )
        session.commit()
    finally:
        session.close()


def run(start: date, end: date) -> None:
    now = datetime.now(timezone.utc)
    stored = 0
    skipped = 0
    with _client() as client:
        current = start
        while current <= end:
            runtime = datetime(current.year, current.month, current.day, 0, 0, tzinfo=timezone.utc)
            rows = fetch_mos_run(client, runtime)
            result = extract_next_day_high(rows, runtime)
            if result is not None:
                target_date, predicted_high = result
                store_forecast(target_date, predicted_high, runtime, rows)
                stored += 1
            else:
                skipped += 1
            current += timedelta(days=1)

    print(
        f"[{now.isoformat()}] Backfilled MOS forecasts {start} to {end}: "
        f"{stored} stored, {skipped} had no usable next-day n_x value."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    run(date.fromisoformat(args.start), date.fromisoformat(args.end))
