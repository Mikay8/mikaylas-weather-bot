"""Cross-market scanner cron entry point: python3 -m weatherbot.ingest.cross_market_scan

Fetches Kalshi + Polymarket (+ Manifold reference) quotes, matches the
same event across venues, and stores one snapshot per matched pair.
Read-only against every external API; the only writes are to our own
cross_market_* tables. No trades are ever placed from this data — it
exists to measure whether executable cross-venue discrepancies survive
fees at all before any trading idea is built on them.

--dry-run prints matches without touching the database.
"""

import sys
from datetime import datetime, timezone

from weatherbot.cross_market import run_scan, store_scan
from weatherbot.db import get_session


def run(dry_run: bool = False) -> dict:
    result = run_scan()
    pairs = result["pairs"]
    now = datetime.now(timezone.utc)

    print(
        f"[{now.isoformat()}] Cross-market scan: "
        f"kalshi={result['kalshi_quotes']} polymarket={result['polymarket_quotes']} "
        f"manifold_attached={result['manifold_attached']} matched_pairs={len(pairs)}"
    )
    for pair in pairs[:15]:
        edge = pair["arb_edge"]
        edge_str = f"{edge:+.4f}" if edge is not None else "n/a"
        print(
            f"  edge={edge_str} gap={pair['mid_gap']} score={pair['match_score']:.2f} "
            f"K:{pair['kalshi'].title[:60]!r} <-> P:{pair['polymarket'].title[:60]!r}"
        )

    if not dry_run:
        session = get_session()
        try:
            written = store_scan(session, pairs)
        finally:
            session.close()
        print(f"[{now.isoformat()}] Stored {written} snapshot(s).")

    return {
        "scanned_at": now.isoformat(),
        "kalshi_quotes": result["kalshi_quotes"],
        "polymarket_quotes": result["polymarket_quotes"],
        "manifold_attached": result["manifold_attached"],
        "pairs_matched": len(pairs),
        "opportunities": sum(1 for p in pairs if (p["arb_edge"] or 0) > 0),
    }


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
