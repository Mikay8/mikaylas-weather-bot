"""Pull Kalshi KXHIGHNY market snapshots (bracket structure, bid/ask, volume,
open interest) and store in `market_snapshots`.

Public market data (GET /markets) does not require authentication.
"""

import json
import re
from datetime import date, datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session

load_dotenv()

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"

# Ticker format: KXHIGHNY-26AUG19-T92 -> event date 2026-08-19
_TICKER_DATE_RE = re.compile(r"KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})-")


def parse_target_date(ticker: str) -> date | None:
    match = _TICKER_DATE_RE.match(ticker)
    if not match:
        return None
    yy, mon, dd = match.groups()
    parsed = datetime.strptime(f"20{yy}-{mon}-{dd}", "%Y-%b-%d")
    return parsed.date()


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, event_hooks=make_logged_hooks("kalshi"))


def fetch_markets(client: httpx.Client) -> list[dict]:
    markets: list[dict] = []
    cursor = None
    while True:
        params = {"series_ticker": SERIES_TICKER, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(f"{KALSHI_BASE}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return markets


def _to_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def implied_prob_from_market(market: dict) -> float | None:
    yes_bid = _to_float(market.get("yes_bid_dollars"))
    yes_ask = _to_float(market.get("yes_ask_dollars"))
    if yes_bid is None or yes_ask is None:
        return None
    return round((yes_bid + yes_ask) / 2, 4)  # dollars are already a 0-1 probability


def store_snapshot(market: dict, timestamp: datetime):
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO market_snapshots
                    (contract_id, timestamp, bracket_low, bracket_high, yes_bid, yes_ask,
                     implied_prob, volume, open_interest, target_date, strike_type, raw_response)
                VALUES
                    (:contract_id, :timestamp, :bracket_low, :bracket_high, :yes_bid, :yes_ask,
                     :implied_prob, :volume, :open_interest, :target_date, :strike_type, :raw_response)
                ON CONFLICT (contract_id, timestamp) DO NOTHING
                """
            ),
            {
                "contract_id": market["ticker"],
                "timestamp": timestamp,
                "bracket_low": market.get("floor_strike"),
                "bracket_high": market.get("cap_strike"),
                "yes_bid": _to_float(market.get("yes_bid_dollars")),
                "yes_ask": _to_float(market.get("yes_ask_dollars")),
                "implied_prob": implied_prob_from_market(market),
                "volume": _to_float(market.get("volume_fp")),
                "open_interest": _to_float(market.get("open_interest_fp")),
                "target_date": parse_target_date(market["ticker"]),
                "strike_type": market.get("strike_type"),
                "raw_response": json.dumps(market),
            },
        )
        session.commit()
    finally:
        session.close()


def run() -> None:
    now = datetime.now(timezone.utc)
    with _client() as client:
        markets = fetch_markets(client)

    if not markets:
        print(f"[{now.isoformat()}] No open {SERIES_TICKER} markets found.")
        return

    for market in markets:
        store_snapshot(market, now)

    print(f"[{now.isoformat()}] Stored {len(markets)} {SERIES_TICKER} market snapshot(s).")


if __name__ == "__main__":
    run()
