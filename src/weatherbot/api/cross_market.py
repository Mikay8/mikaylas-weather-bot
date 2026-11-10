"""Cross-market comparison endpoints: latest snapshot per matched
Kalshi<->Polymarket pair, a summary strip, per-pair history, and a
manual scan trigger (the cron in .railway/railway.ts runs it
hourly; this is for the UI's Scan now button).

All prices are executable bid/ask. arb_edge is net of Kalshi's taker
fee; see cross_market.py for the math and its assumptions.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from weatherbot.db import get_session

router = APIRouter(prefix="/api/cross-market", tags=["cross-market"])

_LATEST_PAIR_SQL = """
    SELECT DISTINCT ON (p.id)
        p.id AS pair_id, p.kalshi_ticker, p.kalshi_event_ticker, p.kalshi_title,
        p.poly_condition_id, p.poly_slug, p.poly_question,
        p.manifold_id, p.manifold_question, p.match_score, p.close_time,
        p.first_seen_at, p.last_seen_at,
        s.scanned_at, s.kalshi_yes_bid, s.kalshi_yes_ask,
        s.poly_yes_bid, s.poly_yes_ask, s.manifold_prob,
        s.mid_gap, s.arb_edge, s.arb_direction, s.kalshi_volume, s.poly_volume
    FROM cross_market_pairs p
    JOIN cross_market_snapshots s ON s.pair_id = p.id
    ORDER BY p.id, s.scanned_at DESC
"""


def _rows(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


@router.get("/pairs")
def list_pairs(min_edge: float | None = None):
    """Latest snapshot per pair, best net arbitrage edge first. Pairs
    whose books were incomplete (arb_edge NULL) sort last."""
    session = get_session()
    try:
        rows = _rows(session.execute(text(_LATEST_PAIR_SQL)))
    except Exception:
        return []  # tables not created yet — no scan has ever run
    finally:
        session.close()
    if min_edge is not None:
        rows = [r for r in rows if r["arb_edge"] is not None and r["arb_edge"] >= min_edge]
    rows.sort(key=lambda r: (r["arb_edge"] is not None, r["arb_edge"] or 0), reverse=True)
    return rows


@router.get("/summary")
def summary():
    session = get_session()
    try:
        try:
            latest = _rows(session.execute(text(_LATEST_PAIR_SQL)))
            totals = session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT pair_id) AS pairs_tracked,
                           COUNT(*) AS snapshots_total,
                           MAX(scanned_at) AS last_scan_at
                    FROM cross_market_snapshots
                    """
                )
            ).fetchone()
        except Exception:
            return {
                "pairs_tracked": 0,
                "snapshots_total": 0,
                "last_scan_at": None,
                "opportunities_now": 0,
                "best_edge_now": None,
                "avg_mid_gap": None,
            }
        edges = [r["arb_edge"] for r in latest if r["arb_edge"] is not None]
        gaps = [r["mid_gap"] for r in latest if r["mid_gap"] is not None]
        return {
            "pairs_tracked": totals.pairs_tracked or 0,
            "snapshots_total": totals.snapshots_total or 0,
            "last_scan_at": totals.last_scan_at,
            "opportunities_now": sum(1 for e in edges if e > 0),
            "best_edge_now": max(edges) if edges else None,
            "avg_mid_gap": round(sum(gaps) / len(gaps), 4) if gaps else None,
        }
    finally:
        session.close()


@router.get("/pairs/{pair_id}/history")
def pair_history(pair_id: int, limit: int = 200):
    session = get_session()
    try:
        rows = _rows(
            session.execute(
                text(
                    """
                    SELECT scanned_at, kalshi_yes_bid, kalshi_yes_ask,
                           poly_yes_bid, poly_yes_ask, manifold_prob,
                           mid_gap, arb_edge, arb_direction
                    FROM cross_market_snapshots
                    WHERE pair_id = :pair_id
                    ORDER BY scanned_at DESC
                    LIMIT :limit
                    """
                ),
                {"pair_id": pair_id, "limit": limit},
            )
        )
    except Exception:
        rows = []
    finally:
        session.close()
    if not rows:
        raise HTTPException(status_code=404, detail="No snapshots for this pair yet")
    return rows


@router.post("/scan")
def trigger_scan():
    """Run one scan synchronously and store it. Takes ~10-30s (three
    public APIs, paginated). The demo deployment can't reach this —
    block_demo_mutations rejects all POSTs from the demo origin."""
    from weatherbot.ingest.cross_market_scan import run as run_scan_once

    try:
        return run_scan_once()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cross-market scan failed: {e}")
