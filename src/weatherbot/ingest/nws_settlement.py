"""Pull the NWS CLI (Climatological Report, Daily) for NYC/Central Park and
store the observed daily high in `settlements`.

NOTE: Kalshi's KXHIGHNY contracts settle "according to The Weather Company,"
not the NWS CLI report (confirmed from live rules_primary text on active
markets, contradicting Kalshi's own Help Center docs). The Weather Company
has no free public API for historical Central Park highs, so this NWS CLI
value is used as a proxy/estimate. The two sources reference the same
station (CLINYC) and should usually agree, but can diverge on close calls.
Revisit before Phase 4 if backtesting shows this proxy causes meaningful
mismatches near bracket edges.
"""

import os
import re
from datetime import date, datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.db import get_session

load_dotenv()

STATION = "NYC_CENTRAL_PARK"
NWS_BASE = "https://api.weather.gov"
SOURCE = "NWS_CLI_NYC"

MONTHS = (
    "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
)
SUMMARY_DATE_RE = re.compile(
    rf"CENTRAL PARK NY CLIMATE SUMMARY FOR ({MONTHS}) (\d{{1,2}}) (\d{{4}})", re.IGNORECASE
)
MAXIMUM_RE = re.compile(r"MAXIMUM\s+(-?\d+)")


def _user_agent() -> str:
    contact = os.environ.get("NWS_USER_AGENT_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("NWS_USER_AGENT_CONTACT must be set in .env")
    return f"(mikaylas-weather-bot, {contact})"


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _user_agent()}, timeout=30.0)


def list_cli_products(client: httpx.Client, limit: int = 40) -> list[dict]:
    resp = client.get(f"{NWS_BASE}/products/types/CLI/locations/NYC")
    resp.raise_for_status()
    return resp.json()["@graph"][:limit]


def fetch_product_text(client: httpx.Client, product_id: str) -> str:
    resp = client.get(f"{NWS_BASE}/products/{product_id}")
    resp.raise_for_status()
    return resp.json()["productText"]


def parse_settlement(text_body: str) -> tuple[date, float] | None:
    date_match = SUMMARY_DATE_RE.search(text_body)
    max_match = MAXIMUM_RE.search(text_body)
    if not date_match or not max_match:
        return None
    month_name, day, year = date_match.groups()
    month = datetime.strptime(month_name.title(), "%B").month
    target_date = date(int(year), month, int(day))
    actual_high = float(max_match.group(1))
    return target_date, actual_high


def store_settlement(target_date: date, actual_high: float, raw_text: str):
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO settlements (station, date, actual_high, source, raw_product_text)
                VALUES (:station, :date, :actual_high, :source, :raw_product_text)
                ON CONFLICT (date) DO NOTHING
                """
            ),
            {
                "station": STATION,
                "date": target_date,
                "actual_high": actual_high,
                "source": SOURCE,
                "raw_product_text": raw_text,
            },
        )
        session.commit()
    finally:
        session.close()


def run(limit: int = 5) -> None:
    now = datetime.now(timezone.utc)
    stored = 0
    with _client() as client:
        products = list_cli_products(client, limit=limit)
        for product in products:
            body = fetch_product_text(client, product["id"])
            parsed = parse_settlement(body)
            if parsed is None:
                continue
            target_date, actual_high = parsed
            store_settlement(target_date, actual_high, body)
            stored += 1

    print(f"[{now.isoformat()}] Processed {len(products)} CLI product(s), stored {stored} settlement(s).")


if __name__ == "__main__":
    run()
