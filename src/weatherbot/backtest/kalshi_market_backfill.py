"""Backfill historical KXHIGHNY market prices from Kalshi's public API.

Only pulls markets that closed on or after 2026-08-14 (SETTLEMENT_SOURCE_CUTOFF),
the date Kalshi's own series metadata confirms they switched KXHIGHNY's
settlement source from NWS to The Weather Company. Data from before that date
was priced against a different settlement expectation, so mixing it in would
make any backtest built on this data internally inconsistent.

Kalshi partitions data into a live API (rolling ~3 month window) and a
separate historical archive for anything older, with the boundary given by
GET /historical/cutoff (market_settled_ts). Markets that settled before that
cutoff are only queryable via the /historical/* endpoints, which use a
different response shape (FixedPointDollars strings, not nested
{close_dollars: ...} dicts) - see fetch_candlesticks_historical below. We
pull each settled market from whichever API actually still has it, so the
backfill isn't silently capped at the live API's 3-month window.

Two-step pull per market:
1. GET /markets or /historical/markets (series_ticker=KXHIGHNY, status=settled)
   - list of closed markets
2. GET /series/KXHIGHNY/markets/{ticker}/candlesticks (live) or
   GET /historical/markets/{ticker}/candlesticks (archived) - hourly OHLC
   price/bid/ask/volume history for that market's lifetime, stored as one
   market_snapshots row per period (using the period's end timestamp), same
   shape live ingest uses so backtests can query both uniformly.
"""

import argparse
import json
from datetime import date, datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from weatherbot.api_logger import make_logged_hooks
from weatherbot.db import get_session
from weatherbot.ingest.kalshi_market import parse_target_date

load_dotenv()

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"
SETTLEMENT_SOURCE_CUTOFF = date(2026, 8, 14)
CANDLESTICK_PERIOD_MINUTES = 60


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, event_hooks=make_logged_hooks("kalshi"))


def fetch_historical_cutoff(client: httpx.Client) -> datetime:
    resp = client.get(f"{KALSHI_BASE}/historical/cutoff")
    resp.raise_for_status()
    raw = resp.json()["market_settled_ts"]
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def fetch_settled_markets(client: httpx.Client, min_close: date) -> list[dict]:
    """Fetch settled markets from both the live and historical market lists.

    Neither API's settled-market listing takes a single date range that spans
    both, so we query each and dedupe by ticker.
    """
    min_close_ts = int(datetime(min_close.year, min_close.month, min_close.day, tzinfo=timezone.utc).timestamp())
    markets_by_ticker: dict[str, dict] = {}

    # Live API: recent settled markets (rolling ~3 month window).
    cursor = None
    while True:
        params = {
            "series_ticker": SERIES_TICKER,
            "status": "settled",
            "limit": 200,
            "min_close_ts": min_close_ts,
        }
        if cursor:
            params["cursor"] = cursor
        resp = client.get(f"{KALSHI_BASE}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        for market in data.get("markets", []):
            markets_by_ticker[market["ticker"]] = market
        cursor = data.get("cursor")
        if not cursor:
            break

    # Historical API: older settled markets, archived past the live window.
    cursor = None
    while True:
        params = {"series_ticker": SERIES_TICKER, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(f"{KALSHI_BASE}/historical/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        for market in data.get("markets", []):
            if market.get("status") != "settled":
                continue
            close_time = datetime.fromisoformat(market["close_time"].replace("Z", "+00:00"))
            if close_time.date() < min_close:
                continue
            markets_by_ticker.setdefault(market["ticker"], market)
        cursor = data.get("cursor")
        if not cursor:
            break

    return list(markets_by_ticker.values())


def fetch_candlesticks(client: httpx.Client, ticker: str, open_ts: int, close_ts: int) -> list[dict]:
    resp = client.get(
        f"{KALSHI_BASE}/series/{SERIES_TICKER}/markets/{ticker}/candlesticks",
        params={
            "period_interval": CANDLESTICK_PERIOD_MINUTES,
            "start_ts": open_ts,
            "end_ts": close_ts,
        },
    )
    resp.raise_for_status()
    return resp.json().get("candlesticks", [])


def fetch_candlesticks_historical(client: httpx.Client, ticker: str, open_ts: int, close_ts: int) -> list[dict]:
    """Same as fetch_candlesticks, but for markets past the live-API cutoff.

    Normalizes the historical response's {yes_bid: {close: "0.5600"}} shape
    into the same {yes_bid: {close_dollars: 0.56}} shape store_candlestick_snapshot
    expects from the live endpoint, so both paths can share one storage function.
    """
    resp = client.get(
        f"{KALSHI_BASE}/historical/markets/{ticker}/candlesticks",
        params={
            "period_interval": CANDLESTICK_PERIOD_MINUTES,
            "start_ts": open_ts,
            "end_ts": close_ts,
        },
    )
    resp.raise_for_status()
    candles = resp.json().get("candlesticks", [])
    normalized = []
    for candle in candles:
        yes_bid = candle.get("yes_bid") or {}
        yes_ask = candle.get("yes_ask") or {}
        normalized.append(
            {
                "end_period_ts": candle["end_period_ts"],
                "yes_bid": {"close_dollars": yes_bid.get("close")},
                "yes_ask": {"close_dollars": yes_ask.get("close")},
                "volume_fp": candle.get("volume"),
                "open_interest_fp": candle.get("open_interest"),
            }
        )
    return normalized


def _to_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def store_candlestick_snapshot(market: dict, candle: dict):
    ticker = market["ticker"]
    yes_bid = _to_float(candle.get("yes_bid", {}).get("close_dollars"))
    yes_ask = _to_float(candle.get("yes_ask", {}).get("close_dollars"))
    implied_prob = round((yes_bid + yes_ask) / 2, 4) if yes_bid is not None and yes_ask is not None else None
    timestamp = datetime.fromtimestamp(candle["end_period_ts"], tz=timezone.utc)

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
                "contract_id": ticker,
                "timestamp": timestamp,
                "bracket_low": market.get("floor_strike"),
                "bracket_high": market.get("cap_strike"),
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "implied_prob": implied_prob,
                "volume": _to_float(candle.get("volume_fp")),
                "open_interest": _to_float(candle.get("open_interest_fp")),
                "target_date": parse_target_date(ticker),
                "strike_type": market.get("strike_type"),
                "raw_response": json.dumps(candle),
            },
        )
        session.commit()
    finally:
        session.close()


def run(min_close: date = SETTLEMENT_SOURCE_CUTOFF, limit: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    with _client() as client:
        cutoff = fetch_historical_cutoff(client)
        markets = fetch_settled_markets(client, min_close)
        if limit is not None:
            markets = markets[:limit]

        total_snapshots = 0
        historical_markets = 0
        for market in markets:
            ticker = market["ticker"]
            open_ts = int(datetime.fromisoformat(market["open_time"].replace("Z", "+00:00")).timestamp())
            close_time = datetime.fromisoformat(market["close_time"].replace("Z", "+00:00"))
            close_ts = int(close_time.timestamp())

            if close_time < cutoff:
                candles = fetch_candlesticks_historical(client, ticker, open_ts, close_ts)
                historical_markets += 1
            else:
                candles = fetch_candlesticks(client, ticker, open_ts, close_ts)

            for candle in candles:
                if candle.get("yes_bid", {}).get("close_dollars") is None and (
                    candle.get("yes_ask", {}).get("close_dollars") is None
                ):
                    continue
                store_candlestick_snapshot(market, candle)
                total_snapshots += 1

    print(
        f"[{now.isoformat()}] Backfilled {len(markets)} settled {SERIES_TICKER} market(s) "
        f"({historical_markets} from the historical archive, cutoff {cutoff.isoformat()}), "
        f"{total_snapshots} snapshot(s), closed on/after {min_close.isoformat()}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max markets to backfill")
    args = parser.parse_args()
    run(limit=args.limit)
