"""Pull Kalshi KXHIGHNY market snapshots (bracket structure, bid/ask, volume,
open interest) and store in `market_snapshots`.

Public market data (GET /markets) does not require authentication.
"""

import json
import random
import re
import time
from datetime import date, datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session

load_dotenv()

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"

# Kalshi returns 429 (and occasionally 5xx) transiently and sends no
# Retry-After header, so retry with exponential backoff + jitter instead
# of crashing the hourly cron run on the first rate-limit response.
MAX_ATTEMPTS = 5
RETRY_BASE_DELAY_SECONDS = 2.0
RETRY_MAX_DELAY_SECONDS = 30.0

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


def _retry_delay(resp: httpx.Response, attempt: int, base_delay: float) -> float:
    retry_after = resp.headers.get("Retry-After") if resp.headers else None
    if retry_after:
        try:
            return min(float(retry_after), RETRY_MAX_DELAY_SECONDS)
        except ValueError:
            pass
    backoff = base_delay * (2 ** (attempt - 1))
    return min(backoff, RETRY_MAX_DELAY_SECONDS) + random.uniform(0, 1)


def _get_markets_page(
    client: httpx.Client,
    params: dict,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    sleep=time.sleep,
) -> dict:
    url = f"{KALSHI_BASE}/markets"
    for attempt in range(1, max_attempts + 1):
        resp = client.get(url, params=params)
        if resp.status_code != 429 and resp.status_code < 500:
            resp.raise_for_status()
            return resp.json()
        if attempt == max_attempts:
            print(
                f"ERROR fetch_markets: Kalshi markets request failed after "
                f"{max_attempts} attempts with HTTP {resp.status_code} for {url} "
                f"(series_ticker={SERIES_TICKER}); giving up."
            )
            resp.raise_for_status()
        delay = _retry_delay(resp, attempt, base_delay)
        print(
            f"WARNING fetch_markets: attempt {attempt}/{max_attempts} got "
            f"HTTP {resp.status_code} for {url} (series_ticker={SERIES_TICKER}); "
            f"retrying in {delay:.1f}s."
        )
        sleep(delay)
    raise RuntimeError("fetch_markets: unreachable retry state")  # pragma: no cover


def fetch_markets(
    client: httpx.Client,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    sleep=time.sleep,
) -> list[dict]:
    markets: list[dict] = []
    cursor = None
    while True:
        params = {"series_ticker": SERIES_TICKER, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = _get_markets_page(
            client, params, max_attempts=max_attempts, base_delay=base_delay, sleep=sleep
        )
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
