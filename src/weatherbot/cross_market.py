"""Cross-market relative-value scanner: the same binary event priced on
Kalshi and Polymarket (with Manifold as an indicative third reference).

This is NOT a forecasting model. It never estimates a "true" probability —
it only records when two venues' executable prices for the same outcome
disagree, which is the one kind of disagreement that doesn't require being
smarter than the market (see the weather-bot post-mortem: model-vs-market
disagreement was model error, every time it was tested).

Honesty rules, same as the backtests:
- Arbitrage math uses executable bid/ask only, never midpoints. Midpoints
  appear solely as a display gap.
- Fees are included in the net edge (Kalshi's published taker fee formula;
  Polymarket currently charges no taker fee on these markets — if that
  changes, update POLY_FEE_RATE and every historical "net" number shifts).
- Matching is precision-first: a false pair fabricates a fake arbitrage,
  which is worse than a missed pair. Numbers in the two titles (years,
  strikes, dates) must not conflict, titles must share >= MIN_SHARED_TOKENS
  distinctive tokens, and close times must be within MAX_CLOSE_SKEW_DAYS.
- Manifold is play-money with an AMM price, not an order book. Its
  probability is stored/displayed as a reference only and is NEVER used
  in arbitrage math.
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
POLY_GAMMA_BASE = "https://gamma-api.polymarket.com"
MANIFOLD_BASE = "https://api.manifold.markets/v0"

MATCH_THRESHOLD = 0.55
MIN_SHARED_TOKENS = 3
MAX_CLOSE_SKEW_DAYS = 45

KALSHI_FEE_COEF = 0.07  # taker fee per contract = coef * p * (1 - p)
POLY_FEE_RATE = 0.0

_STOPWORDS = {
    "will", "the", "a", "an", "in", "on", "by", "of", "to", "be", "is",
    "are", "was", "were", "at", "for", "and", "or", "before", "after",
    "during", "market", "yes", "no", "this", "that", "with", "from",
    "have", "has", "their", "its", "it", "as", "if", "than", "then",
}

_TOKEN_RE = re.compile(r"[a-z0-9$%,.']+")

# Light normalization so the same event phrased slightly differently on
# two venues still matches ("Federal Reserve" vs "Fed", "rates" vs "rate").
_ALIASES = {"federal": "fed"}


def _stem(tok: str) -> str:
    if tok in _ALIASES:
        return _ALIASES[tok]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


@dataclass
class VenueQuote:
    source: str  # 'kalshi' | 'polymarket' | 'manifold'
    market_id: str
    title: str
    url: str | None
    yes_bid: float | None
    yes_ask: float | None
    close_time: datetime | None
    volume: float | None
    event_ref: str | None = None  # kalshi event ticker / poly event slug
    outcome: str | None = None  # mutually-exclusive outcome name, if any

    @property
    def mid(self) -> float | None:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return (self.yes_bid + self.yes_ask) / 2


def tokenize(text_value: str) -> set[str]:
    tokens = set()
    for raw in _TOKEN_RE.findall(text_value.lower().replace("&", " and ")):
        tok = raw.strip(".'")
        if not tok or tok in _STOPWORDS:
            continue
        tokens.add(_stem(tok))
    return tokens


def _number_tokens(tokens: set[str]) -> set[str]:
    # Normalized so "$100,000" and "100000" count as the same number.
    return {
        t.replace(",", "").replace("$", "").replace("%", "")
        for t in tokens
        if any(ch.isdigit() for ch in t)
    }


def _score_token_sets(ta: set[str], tb: set[str]) -> float:
    if not ta or not tb:
        return 0.0
    shared = ta & tb
    if len(shared) < MIN_SHARED_TOKENS:
        return 0.0
    nums_a, nums_b = _number_tokens(ta), _number_tokens(tb)
    if nums_a and nums_b and nums_a.isdisjoint(nums_b):
        return 0.0
    containment = len(shared) / min(len(ta), len(tb))
    jaccard = len(shared) / len(ta | tb)
    return round(0.65 * containment + 0.35 * jaccard, 4)


def score_match(text_a: str, text_b: str) -> float:
    """0..1 similarity for two market titles. 0 means 'definitely not the
    same event' (too few shared tokens, or conflicting numbers)."""
    return _score_token_sets(tokenize(text_a), tokenize(text_b))


def kalshi_fee(price: float) -> float:
    return KALSHI_FEE_COEF * price * (1 - price)


def poly_fee(price: float) -> float:
    return POLY_FEE_RATE * price * (1 - price)


def best_arbitrage(kalshi: VenueQuote, poly: VenueQuote) -> dict | None:
    """Best hedged pair trade between the two venues, or None if either
    book is incomplete. Buying YES on one venue and NO on the other locks
    a $1 payout at settlement; edge = 1 - total cost - fees. Edge is
    usually negative (that's the spread) — it is recorded either way so
    the UI shows how far from tradeable each pair is."""
    directions = []

    if kalshi.yes_ask is not None and poly.yes_bid is not None:
        no_price_poly = 1 - poly.yes_bid
        cost = kalshi.yes_ask + no_price_poly
        fees = kalshi_fee(kalshi.yes_ask) + poly_fee(no_price_poly)
        directions.append(
            {
                "direction": "buy_yes_kalshi_buy_no_polymarket",
                "cost": round(cost, 4),
                "edge": round(1 - cost - fees, 4),
            }
        )
    if poly.yes_ask is not None and kalshi.yes_bid is not None:
        no_price_kalshi = 1 - kalshi.yes_bid
        cost = poly.yes_ask + no_price_kalshi
        fees = poly_fee(poly.yes_ask) + kalshi_fee(no_price_kalshi)
        directions.append(
            {
                "direction": "buy_yes_polymarket_buy_no_kalshi",
                "cost": round(cost, 4),
                "edge": round(1 - cost - fees, 4),
            }
        )
    if not directions:
        return None
    return max(directions, key=lambda d: d["edge"])


# ---------------------------------------------------------------------------
# Fetchers (all public, unauthenticated reads — same as the weather bot's
# Kalshi usage). No api_logger hooks: Gamma/CLOB responses are megabytes,
# and api_call_logs truncates at 4k chars anyway; the scanner's own
# snapshot tables are its audit trail.
# ---------------------------------------------------------------------------


def _get_json(client: httpx.Client, url: str, params: dict | None = None) -> dict | list:
    """GET with retry on 429/5xx (the market-cron 429 lesson, PR #14)."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            last_exc = e
            if attempt < 2:
                time.sleep(2**attempt)
    raise last_exc  # type: ignore[misc]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _valid_bid(value: float | None) -> float | None:
    # A 0.00 bid means nobody is bidding — there is no executable sell
    # price, so for pricing purposes it is missing, not zero.
    if value is None or value <= 0:
        return None
    return value


def _valid_ask(value: float | None) -> float | None:
    # A 1.00 ask is equally un-executable (paying full value for a
    # contract worth at most $1) — mirrors trading.py's price rule.
    if value is None or value >= 1:
        return None
    return value


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_kalshi_quotes(client: httpx.Client, max_events: int = 2000) -> list[VenueQuote]:
    """Open Kalshi events with nested markets. The flat /markets firehose
    is unusable for this (thousands of MVE parlay legs sort first), so we
    walk /events and skip multivariate series outright."""
    quotes: list[VenueQuote] = []
    cursor = None
    seen_events = 0
    while seen_events < max_events:
        params: dict = {"status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        data = _get_json(client, f"{KALSHI_BASE}/events", params=params)
        events = data.get("events", []) if isinstance(data, dict) else []
        if not events:
            break
        for event in events:
            seen_events += 1
            series = event.get("series_ticker") or ""
            if "MVE" in series:
                continue
            event_title = event.get("title") or ""
            for market in event.get("markets", []):
                if market.get("market_type") not in (None, "binary"):
                    continue
                yes_bid = _valid_bid(_to_float(market.get("yes_bid_dollars")))
                yes_ask = _valid_ask(_to_float(market.get("yes_ask_dollars")))
                if yes_bid is None and yes_ask is None:
                    continue
                sub = market.get("yes_sub_title") or ""
                title = event_title if not sub or sub.lower() in event_title.lower() else f"{event_title} — {sub}"
                quotes.append(
                    VenueQuote(
                        source="kalshi",
                        market_id=market["ticker"],
                        title=title,
                        url=f"https://kalshi.com/markets/{event.get('event_ticker', '')}",
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        close_time=_parse_ts(market.get("close_time")),
                        volume=_to_float(market.get("volume_fp")),
                        event_ref=event.get("event_ticker"),
                        outcome=sub or None,
                    )
                )
        cursor = data.get("cursor") if isinstance(data, dict) else None
        if not cursor:
            break
    return quotes


def fetch_polymarket_quotes(client: httpx.Client) -> list[VenueQuote]:
    """Active Polymarket markets (Gamma API). Includes single-outcome
    markets of multi-outcome events (groupItemTitle), which is how
    Polymarket represents the same 'who/what' questions Kalshi lists as
    mutually exclusive events.

    Slices: top by 24h volume (10 pages) + top by liquidity (5 pages),
    deduped. Gamma caps every response at 100 markets regardless of the
    limit parameter, so pagination is by offset with page size 100. The
    24h-volume front page alone is all same-day sports/esports; the
    politics/economics/crypto markets that actually overlap with Kalshi
    sit deeper and are longer-lived, which the liquidity slice catches."""
    raw: list[dict] = []
    seen: set[str] = set()
    page_plans = [("volume24hr", 10), ("liquidity", 5)]
    for order, pages in page_plans:
        for page in range(pages):
            data = _get_json(
                client,
                f"{POLY_GAMMA_BASE}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "order": order,
                    "ascending": "false",
                    "limit": 100,
                    "offset": page * 100,
                },
            )
            batch = data if isinstance(data, list) else []
            for market in batch:
                cid = market.get("conditionId") or market.get("id")
                if cid and cid not in seen:
                    seen.add(cid)
                    raw.append(market)
            if len(batch) < 100:
                break

    quotes: list[VenueQuote] = []
    for market in raw:
        if market.get("acceptingOrders") is False:
            continue
        try:
            outcomes = json.loads(market.get("outcomes") or "[]")
        except (TypeError, ValueError):
            continue
        group_item = market.get("groupItemTitle")
        if not group_item and [o.lower() for o in outcomes] != ["yes", "no"]:
            continue
        yes_bid = _valid_bid(_to_float(market.get("bestBid")))
        yes_ask = _valid_ask(_to_float(market.get("bestAsk")))
        if yes_bid is None and yes_ask is None:
            continue
        question = market.get("question") or ""
        title = (
            question
            if not group_item or group_item.lower() in question.lower()
            else f"{question} — {group_item}"
        )
        quotes.append(
            VenueQuote(
                source="polymarket",
                market_id=market.get("conditionId") or market.get("id") or "",
                title=title,
                url=f"https://polymarket.com/market/{market.get('slug', '')}",
                yes_bid=yes_bid,
                yes_ask=yes_ask,
                close_time=_parse_ts(market.get("endDate")),
                volume=_to_float(market.get("volume24hr")),
                event_ref=market.get("slug"),
                outcome=group_item or None,
            )
        )
    return quotes


def fetch_manifold_quotes(client: httpx.Client, limit: int = 1000) -> list[VenueQuote]:
    """Manifold binary markets (public API, no key). Play-money AMM: the
    probability is an indicative reference only — bid=ask=probability is a
    display convenience, never an executable quote."""
    data = _get_json(client, f"{MANIFOLD_BASE}/markets", params={"limit": limit})
    quotes: list[VenueQuote] = []
    for market in data if isinstance(data, list) else []:
        if market.get("outcomeType") != "BINARY" or market.get("isResolved"):
            continue
        prob = _to_float(market.get("probability"))
        if prob is None or prob <= 0 or prob >= 1:
            continue
        if (_to_float(market.get("volume")) or 0) < 100:
            continue
        close_ms = market.get("closeTime")
        quotes.append(
            VenueQuote(
                source="manifold",
                market_id=market.get("id") or "",
                title=market.get("question") or "",
                url=market.get("url"),
                yes_bid=prob,
                yes_ask=prob,
                close_time=datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc) if close_ms else None,
                volume=_to_float(market.get("volume")),
            )
        )
    return quotes


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _close_times_compatible(a: VenueQuote, b: VenueQuote) -> bool:
    """Close-time veto, near-term only. For events resolving within ~75
    days, timing is part of the event's identity (this week's game vs
    next week's). For long-horizon questions ('next PM of Israel'), the
    venues set wildly different administrative close dates for the same
    event, so a skew veto would kill true pairs — token/number agreement
    has to carry those."""
    if a.close_time is None or b.close_time is None:
        return True
    now = datetime.now(timezone.utc)
    horizon_days = (max(a.close_time, b.close_time) - now).total_seconds() / 86400
    if horizon_days > 75:
        return True
    return abs((a.close_time - b.close_time).total_seconds()) <= MAX_CLOSE_SKEW_DAYS * 86400


def match_quotes(
    a: VenueQuote,
    b: VenueQuote,
    tokens_a: set[str] | None = None,
    tokens_b: set[str] | None = None,
) -> float:
    """Full pair score: title similarity, plus two vetoes.
    - Outcome identity: in mutually exclusive events ('Who will be the
      next PM? — <name>'), the shared question makes different candidates
      score deceptively high; the outcome name IS the identity, so if
      either side names an outcome, its tokens must all appear in the
      other side's title.
    - Specificity symmetry: a narrow event's title almost fully contains
      a broad event's tokens ('Ohio House District 27 winner' vs 'control
      the House'), so containment of the smaller set is not enough —
      shared tokens must also cover >= 55% of the LARGER title."""
    if tokens_a is None:
        tokens_a = tokenize(a.title)
    if tokens_b is None:
        tokens_b = tokenize(b.title)
    score = _score_token_sets(tokens_a, tokens_b)
    if score < MATCH_THRESHOLD:
        return 0.0
    if not _close_times_compatible(a, b):
        return 0.0
    shared = tokens_a & tokens_b
    if len(shared) / max(len(tokens_a), len(tokens_b)) < 0.55:
        return 0.0
    for quote, other_tokens in ((a, tokens_b), (b, tokens_a)):
        if quote.outcome:
            outcome_tokens = tokenize(quote.outcome)
            # Venue boilerplate outcomes ("Match Winner", "Game 1 Winner")
            # carry no identity — only veto on substantive names/values.
            substantive = {t for t in outcome_tokens if t not in {"winner", "match", "game"}}
            if substantive and not substantive.issubset(other_tokens):
                return 0.0
    return score


def match_pairs(
    kalshi_quotes: list[VenueQuote],
    poly_quotes: list[VenueQuote],
) -> list[dict]:
    """Greedy best-score matching: each Kalshi market pairs with at most
    one Polymarket market and vice versa, highest scores first, so a
    popular event can't fan out into duplicate pairs. Token sets are
    computed once per quote and an inverted index prefilters pairs that
    share no token at all — the naive double loop is ~7M comparisons."""
    k_tokens = [tokenize(q.title) for q in kalshi_quotes]
    p_tokens = [tokenize(q.title) for q in poly_quotes]
    index: dict[str, list[int]] = {}
    for pi, toks in enumerate(p_tokens):
        for tok in toks:
            index.setdefault(tok, []).append(pi)

    candidates: list[tuple[float, int, int]] = []
    for ki, k in enumerate(kalshi_quotes):
        seen_pi: set[int] = set()
        for tok in k_tokens[ki]:
            for pi in index.get(tok, []):
                if pi in seen_pi:
                    continue
                seen_pi.add(pi)
                score = match_quotes(k, poly_quotes[pi], k_tokens[ki], p_tokens[pi])
                if score > 0:
                    candidates.append((score, ki, pi))
    candidates.sort(reverse=True)

    used_k: set[int] = set()
    used_p: set[int] = set()
    pairs: list[dict] = []
    for score, ki, pi in candidates:
        if ki in used_k or pi in used_p:
            continue
        used_k.add(ki)
        used_p.add(pi)
        k, p = kalshi_quotes[ki], poly_quotes[pi]
        arb = best_arbitrage(k, p)
        mid_gap = None
        if k.mid is not None and p.mid is not None:
            mid_gap = round(abs(k.mid - p.mid), 4)
        pairs.append(
            {
                "kalshi": k,
                "polymarket": p,
                "manifold": None,
                "match_score": score,
                "mid_gap": mid_gap,
                "arb_edge": arb["edge"] if arb else None,
                "arb_direction": arb["direction"] if arb else None,
            }
        )
    pairs.sort(key=lambda d: (d["arb_edge"] is not None, d["arb_edge"] or 0), reverse=True)
    return pairs


def _manifold_quote_from_market(market: dict) -> VenueQuote | None:
    if market.get("outcomeType") != "BINARY" or market.get("isResolved"):
        return None
    prob = _to_float(market.get("probability"))
    if prob is None or prob <= 0 or prob >= 1:
        return None
    close_ms = market.get("closeTime")
    return VenueQuote(
        source="manifold",
        market_id=market.get("id") or "",
        title=market.get("question") or "",
        url=market.get("url"),
        yes_bid=prob,
        yes_ask=prob,
        close_time=datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc) if close_ms else None,
        volume=_to_float(market.get("volume")),
    )


def enrich_manifold(client: httpx.Client, pairs: list[dict]) -> int:
    """Attach a Manifold reference quote to each pair via Manifold's
    search API (its /markets firehose is newest-first junk, unusable for
    discovery). Search terms = the pair's shared distinctive tokens.
    Reference only — never used in arbitrage math. Returns attach count."""
    attached = 0
    for pair in pairs:
        shared = tokenize(pair["kalshi"].title) & tokenize(pair["polymarket"].title)
        terms = sorted(shared, key=len, reverse=True)[:3]
        if not terms:
            continue
        try:
            data = _get_json(
                client,
                f"{MANIFOLD_BASE}/search-markets",
                params={"term": " ".join(terms), "filter": "open", "limit": 20},
            )
        except Exception:
            continue
        best: tuple[float, VenueQuote] | None = None
        for market in data if isinstance(data, list) else []:
            mq = _manifold_quote_from_market(market)
            if mq is None:
                continue
            m_score = max(score_match(pair["kalshi"].title, mq.title), score_match(pair["polymarket"].title, mq.title))
            if m_score >= 0.5 and (best is None or m_score > best[0]):
                best = (m_score, mq)
        if best is not None:
            pair["manifold"] = best[1]
            attached += 1
    return attached


def run_scan() -> dict:
    """Fetch all sources, match, and return matched pairs (no storage)."""
    with httpx.Client(timeout=30.0) as client:
        kalshi = fetch_kalshi_quotes(client)
        poly = fetch_polymarket_quotes(client)
        pairs = match_pairs(kalshi, poly)
        try:
            manifold_attached = enrich_manifold(client, pairs)
        except Exception:
            manifold_attached = 0  # reference-only source: never fail a scan over it
    return {
        "kalshi_quotes": len(kalshi),
        "polymarket_quotes": len(poly),
        "manifold_attached": manifold_attached,
        "pairs": pairs,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS cross_market_pairs (
    id SERIAL PRIMARY KEY,
    kalshi_ticker TEXT NOT NULL,
    kalshi_event_ticker TEXT,
    kalshi_title TEXT NOT NULL,
    poly_condition_id TEXT NOT NULL,
    poly_slug TEXT,
    poly_question TEXT NOT NULL,
    manifold_id TEXT,
    manifold_question TEXT,
    match_score DOUBLE PRECISION NOT NULL,
    close_time TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kalshi_ticker, poly_condition_id)
);
CREATE TABLE IF NOT EXISTS cross_market_snapshots (
    id SERIAL PRIMARY KEY,
    pair_id INTEGER NOT NULL REFERENCES cross_market_pairs(id) ON DELETE CASCADE,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kalshi_yes_bid DOUBLE PRECISION,
    kalshi_yes_ask DOUBLE PRECISION,
    poly_yes_bid DOUBLE PRECISION,
    poly_yes_ask DOUBLE PRECISION,
    manifold_prob DOUBLE PRECISION,
    mid_gap DOUBLE PRECISION,
    arb_edge DOUBLE PRECISION,
    arb_direction TEXT,
    kalshi_volume DOUBLE PRECISION,
    poly_volume DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_xm_snapshots_pair_time
    ON cross_market_snapshots (pair_id, scanned_at DESC);
"""


def ensure_tables(session) -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            session.execute(text(statement))
    session.commit()


def store_scan(session, pairs: list[dict]) -> int:
    """Upsert pairs and append one snapshot per pair. Returns snapshots
    written. Snapshots older than 30 days are pruned — this is a live
    comparison feed, not an audit trail."""
    ensure_tables(session)
    now = datetime.now(timezone.utc)
    written = 0
    for pair in pairs:
        k: VenueQuote = pair["kalshi"]
        p: VenueQuote = pair["polymarket"]
        m: VenueQuote | None = pair["manifold"]
        row = session.execute(
            text(
                """
                INSERT INTO cross_market_pairs
                    (kalshi_ticker, kalshi_event_ticker, kalshi_title,
                     poly_condition_id, poly_slug, poly_question,
                     manifold_id, manifold_question, match_score, close_time, last_seen_at)
                VALUES
                    (:kt, :ke, :kti, :pc, :ps, :pq, :mi, :mq, :ms, :ct, :now)
                ON CONFLICT (kalshi_ticker, poly_condition_id) DO UPDATE SET
                    kalshi_title = EXCLUDED.kalshi_title,
                    poly_question = EXCLUDED.poly_question,
                    manifold_id = EXCLUDED.manifold_id,
                    manifold_question = EXCLUDED.manifold_question,
                    match_score = EXCLUDED.match_score,
                    close_time = EXCLUDED.close_time,
                    last_seen_at = EXCLUDED.last_seen_at
                RETURNING id
                """
            ),
            {
                "kt": k.market_id,
                "ke": k.event_ref,
                "kti": k.title,
                "pc": p.market_id,
                "ps": p.event_ref,
                "pq": p.title,
                "mi": m.market_id if m else None,
                "mq": m.title if m else None,
                "ms": pair["match_score"],
                "ct": k.close_time or p.close_time,
                "now": now,
            },
        ).fetchone()
        session.execute(
            text(
                """
                INSERT INTO cross_market_snapshots
                    (pair_id, scanned_at, kalshi_yes_bid, kalshi_yes_ask,
                     poly_yes_bid, poly_yes_ask, manifold_prob, mid_gap,
                     arb_edge, arb_direction, kalshi_volume, poly_volume)
                VALUES
                    (:pid, :now, :kb, :ka, :pb, :pa, :mp, :gap, :edge, :dir, :kv, :pv)
                """
            ),
            {
                "pid": row.id,
                "now": now,
                "kb": k.yes_bid,
                "ka": k.yes_ask,
                "pb": p.yes_bid,
                "pa": p.yes_ask,
                "mp": m.yes_bid if m else None,
                "gap": pair["mid_gap"],
                "edge": pair["arb_edge"],
                "dir": pair["arb_direction"],
                "kv": k.volume,
                "pv": p.volume,
            },
        )
        written += 1
    session.execute(
        text("DELETE FROM cross_market_snapshots WHERE scanned_at < now() - interval '30 days'")
    )
    session.commit()
    return written
