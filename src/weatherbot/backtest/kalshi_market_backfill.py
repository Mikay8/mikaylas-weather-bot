"""Backfill historical KXHIGHNY market prices from Kalshi's public API.

Only pulls markets that closed on or after 2026-08-14 (SETTLEMENT_SOURCE_CUTOFF),
the date Kalshi's own series metadata confirms they switched KXHIGHNY's
settlement source from NWS to The Weather Company. Data from before that date
was priced against a different settlement expectation, so mixing it in would
make any backtest built on this data internally inconsistent. Kalshi's API
also only exposes settled markets back to roughly late June anyway - there is
no multi-year archive available here the way there is for weather data.

Two-step pull per market:
1. GET /markets?series_ticker=KXHIGHNY&status=settled - list of closed markets
2. GET /series/KXHIGHNY/markets/{ticker}/candlesticks - hourly OHLC price/bid/
   ask/volume history for that market's lifetime, stored as one market_snapshots
   row per period (using the period's end timestamp), same shape live ingest
   uses so backtests can query both uniformly.
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


def fetch_settled_markets(client: httpx.Client, min_close: date) -> list[dict]:
    markets: list[dict] = []
    cursor = None
    min_close_ts = int(datetime(min_close.year, min_close.month, min_close.day, tzinfo=timezone.utc).timestamp())
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
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return markets


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
        markets = fetch_settled_markets(client, min_close)
        if limit is not None:
            markets = markets[:limit]

        total_snapshots = 0
        for market in markets:
            ticker = market["ticker"]
            open_ts = int(datetime.fromisoformat(market["open_time"].replace("Z", "+00:00")).timestamp())
            close_ts = int(datetime.fromisoformat(market["close_time"].replace("Z", "+00:00")).timestamp())
            candles = fetch_candlesticks(client, ticker, open_ts, close_ts)
            for candle in candles:
                if candle.get("yes_bid") is None and candle.get("yes_ask") is None:
                    continue
                store_candlestick_snapshot(market, candle)
                total_snapshots += 1

    print(
        f"[{now.isoformat()}] Backfilled {len(markets)} settled {SERIES_TICKER} market(s), "
        f"{total_snapshots} snapshot(s), closed on/after {min_close.isoformat()}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max markets to backfill")
    args = parser.parse_args()
    run(limit=args.limit)
