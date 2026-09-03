"""Analytics tab endpoints: the nightly Claude analyst's per-trade
diagnoses and calibration-proposal history (see weatherbot/analysis/).
Read-only - this surfaces what the analyst found, it never triggers a run
or touches trading parameters from here.
"""

from fastapi import APIRouter
from sqlalchemy import text

from weatherbot.db import get_session

router = APIRouter(prefix="/api/analytics")


@router.get("/diagnoses")
def get_diagnoses(limit: int = 100):
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT td.id, td.trade_id, td.category, td.confidence, td.summary,
                       td.model, td.created_at,
                       t.target_date, t.side, t.price, t.size, t.pnl, t.is_bot_trade
                FROM trade_diagnoses td
                JOIN trades t ON t.id = td.trade_id
                ORDER BY td.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


@router.get("/calibration-proposals")
def get_calibration_proposals(limit: int = 50):
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, outcome, reasoning, old_factor, new_factor, pr_url,
                       diagnosis_ids, created_at
                FROM calibration_proposals
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


@router.get("/summary")
def get_summary():
    """Category breakdown across all diagnoses, for a quick top-of-page
    rollup (e.g. "9 bad_luck / 2 data_bug / 1 other, last 30 days")."""
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT category, count(*) AS n
                FROM trade_diagnoses
                WHERE created_at > now() - interval '30 days'
                GROUP BY category
                """
            )
        ).fetchall()
        open_pr_count = session.execute(
            text("SELECT count(*) FROM calibration_proposals WHERE outcome = 'pr_opened'")
        ).scalar()
        return {
            "by_category_30d": {r.category: r.n for r in rows},
            "total_prs_opened": open_pr_count,
        }
    finally:
        session.close()
