"""Backfill historical settlements (observed daily high) from IEM's ASOS
daily summary API — free, no key, station NYC (Central Park), back to 2000+.

Used as a proxy for Kalshi's real settlement source ("The Weather Company"
per live market rules_primary text) since no free API exists for that.
Cross-checked against NWS CLI for 8 recent days: 6/8 matched exactly,
2/8 were off by exactly 1F (IEM lower) — treated as acceptable proxy
noise rather than a bug. See weatherbot-data-sources memory for detail.
"""

import argparse
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.db import get_session

load_dotenv()

STATION = "NYC_CENTRAL_PARK"
IEM_STATION = "NYC"
IEM_NETWORK = "NY_ASOS"
IEM_BASE = "https://mesonet.agron.iastate.edu/api/1"
SOURCE = "IEM_ASOS_NYC"


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def fetch_daily_max(client: httpx.Client, target_date: date) -> float | None:
    resp = client.get(
        f"{IEM_BASE}/daily.json",
        params={"station": IEM_STATION, "network": IEM_NETWORK, "date": target_date.isoformat()},
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    if not data:
        return None
    return data[0]["max_tmpf"]


def store_settlement(target_date: date, actual_high: float):
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO settlements (station, date, actual_high, source)
                VALUES (:station, :date, :actual_high, :source)
                ON CONFLICT (date) DO NOTHING
                """
            ),
            {"station": STATION, "date": target_date, "actual_high": actual_high, "source": SOURCE},
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
            max_temp = fetch_daily_max(client, current)
            if max_temp is not None:
                store_settlement(current, max_temp)
                stored += 1
            else:
                skipped += 1
            current += timedelta(days=1)

    print(
        f"[{now.isoformat()}] Backfilled {start} to {end}: "
        f"{stored} settlement(s) attempted, {skipped} date(s) had no IEM data."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    run(date.fromisoformat(args.start), date.fromisoformat(args.end))
