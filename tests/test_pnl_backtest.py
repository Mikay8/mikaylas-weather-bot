"""Unit tests for the honest backtest (pnl_backtest.py).

All fixtures are synthetic and run against an in-memory SQLite database -
no DATABASE_URL, no network. Each test pins one honest-backtest semantic:

 1. one position per target_date (highest favorite_prob contract wins)
 2. fills price at the latest snapshot at-or-before the 08:10 UTC decision
 3. a forecast issued after decision time is never usable (no lookahead)
 4. no qualifying forecast -> the date is skipped, no trade
 5. walk-forward error fit uses only strictly-prior settlement dates whose
    own forecasts were also pre-decision
 6. near_edge flag + PnL reported with/without near-edge trades
 7. threshold reports split train (< split_date) / test (>= split_date)
 8. a contract with no valid price produces no trade
"""

import math
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from weatherbot.backtest.model import (
    STDEV_INFLATION_FACTOR,
    ErrorStats,
    bracket_probability,
)
from weatherbot.backtest.pnl_backtest import (
    decision_time_for,
    prior_errors_for,
    run,
)


def utc_dt(d: date, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT, forecast_time TIMESTAMP, target_date DATE,
                    predicted_high NUMERIC, confidence_low NUMERIC,
                    confidence_high NUMERIC, model_source TEXT, raw_response TEXT)"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id TEXT, timestamp TIMESTAMP,
                    bracket_low NUMERIC, bracket_high NUMERIC,
                    yes_bid NUMERIC, yes_ask NUMERIC, implied_prob NUMERIC,
                    volume NUMERIC, open_interest NUMERIC, raw_response TEXT,
                    target_date DATE, strike_type TEXT)"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT, date DATE UNIQUE, actual_high NUMERIC,
                    source TEXT, raw_product_text TEXT)"""
            )
        )
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def add_settlement(session, d: date, actual: float):
    session.execute(
        text("INSERT INTO settlements (date, actual_high) VALUES (:d, :a)"),
        {"d": d, "a": actual},
    )
    session.commit()


def add_forecast(
    session,
    target_date: date,
    predicted: float,
    forecast_time: datetime,
    source: str = "GFS_MOS",
):
    session.execute(
        text(
            """INSERT INTO forecasts
                   (target_date, predicted_high, forecast_time, model_source)
               VALUES (:d, :p, :ft, :s)"""
        ),
        {"d": target_date, "p": predicted, "ft": forecast_time, "s": source},
    )
    session.commit()


def add_snapshot(
    session,
    contract_id: str,
    target_date: date,
    ts: datetime,
    strike_type: str,
    low: float,
    high: float,
    bid: float,
    ask: float,
    implied: float | None = None,
):
    session.execute(
        text(
            """INSERT INTO market_snapshots
                   (contract_id, target_date, timestamp, strike_type,
                    bracket_low, bracket_high, yes_bid, yes_ask, implied_prob)
               VALUES (:c, :d, :ts, :st, :lo, :hi, :bid, :ask, :imp)"""
        ),
        {
            "c": contract_id,
            "d": target_date,
            "ts": ts,
            "st": strike_type,
            "lo": low,
            "hi": high,
            "bid": bid,
            "ask": ask,
            "imp": implied,
        },
    )
    session.commit()


def seed_error_history(session, first: date, n: int):
    """n past dates, actual 70F, alternating +/-1F GFS_MOS errors.

    Gives the walk-forward fit a known history: bias 0, sample variance 1.2
    (so stdev = sqrt(1.2) * STDEV_INFLATION_FACTOR via the seasonal fallback,
    since n < MIN_SEASONAL_SAMPLES=20).
    """
    for i in range(n):
        d = first + timedelta(days=i)
        err = 1.0 if i % 2 == 0 else -1.0
        add_settlement(session, d, 70.0)
        add_forecast(session, d, 70.0 - err, utc_dt(d, 0, 0))


def test_decision_time_is_0810_utc_on_target_date():
    assert decision_time_for(date(2026, 10, 5)) == datetime(
        2026, 10, 5, 8, 10, tzinfo=UTC
    )


def test_one_position_per_day_highest_favorite_prob_wins(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.45)
    add_snapshot(session, "C2", d, utc_dt(d, 7, 0), "between", 72, 73, 0.10, 0.15)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    assert out["n_target_dates_traded"] == 1
    assert len(out["trades"]) == 1
    # expected winner computed with the same model the backtest uses
    stats = ErrorStats(bias=0.0, stdev=math.sqrt(1.2) * STDEV_INFLATION_FACTOR, n=6)
    p1 = bracket_probability(70.0, stats, "between", 70.0, 71.0)
    p2 = bracket_probability(70.0, stats, "between", 72.0, 73.0)
    expected = "C1" if max(p1, 1 - p1) >= max(p2, 1 - p2) else "C2"
    assert out["trades"][0]["contract_id"] == expected


def test_prices_at_latest_snapshot_before_decision_time(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    add_snapshot(session, "C1", d, utc_dt(d, 6, 0), "between", 70, 71, 0.40, 0.60)
    add_snapshot(session, "C1", d, utc_dt(d, 7, 30), "between", 70, 71, 0.40, 0.80)
    # quoted after the 08:10 decision - must never be used
    add_snapshot(session, "C1", d, utc_dt(d, 9, 0), "between", 70, 71, 0.40, 0.99)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    t = out["trades"][0]
    assert t["price"] == pytest.approx(0.80)
    assert t["snapshot_time"] == utc_dt(d, 7, 30).isoformat()


def test_forecast_issued_after_decision_time_is_not_usable(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    # the only GFS_MOS row was issued at 09:00, after the 08:10 decision
    add_forecast(session, d, 70.0, utc_dt(d, 9, 0))
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.60)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    assert out["n_target_dates_traded"] == 0
    assert out["n_target_dates_skipped_no_forecast"] == 1
    assert out["trades"] == []


def test_no_forecast_at_all_skips_the_date(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.60)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    assert out["n_target_dates_traded"] == 0
    assert out["n_target_dates_skipped_no_forecast"] == 1


def test_prior_errors_exclude_current_future_and_late_forecast_dates():
    dated = [
        (date(2026, 9, 28), 1.0, utc_dt(date(2026, 9, 28), 0, 0)),
        # the target date itself: excluded (walk-forward)
        (date(2026, 10, 5), 99.0, utc_dt(date(2026, 10, 5), 0, 0)),
        # future date: excluded
        (date(2026, 10, 6), 99.0, utc_dt(date(2026, 10, 6), 0, 0)),
        # forecast issued after its own decision time: excluded
        (date(2026, 9, 29), -1.0, utc_dt(date(2026, 9, 30), 9, 0)),
    ]
    assert prior_errors_for(dated, date(2026, 10, 5)) == [(date(2026, 9, 28), 1.0)]


def test_near_edge_flag_and_pnl_split(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d1 = date(2026, 10, 5)
    add_settlement(session, d1, 71.0)  # exactly on the bracket edge
    add_forecast(session, d1, 70.0, utc_dt(d1, 0, 0))
    add_snapshot(session, "C1", d1, utc_dt(d1, 7, 0), "between", 70, 71, 0.40, 0.60)
    d2 = date(2026, 10, 6)
    add_settlement(session, d2, 69.0)  # a full degree from either edge
    add_forecast(session, d2, 70.0, utc_dt(d2, 0, 0))
    add_snapshot(session, "C2", d2, utc_dt(d2, 7, 0), "between", 70, 71, 0.40, 0.60)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    by_id = {t["contract_id"]: t for t in out["trades"]}
    assert by_id["C1"]["near_edge"] is True
    assert by_id["C2"]["near_edge"] is False
    nea = out["near_edge_analysis"]
    assert nea["n_near_edge_trades"] == 1
    assert nea["all_trades"]["n_trades"] == 2
    assert nea["excluding_near_edge_trades"]["n_trades"] == 1


def test_threshold_reports_split_train_and_test(session):
    seed_error_history(session, date(2026, 9, 1), 10)
    d_train = date(2026, 9, 20)
    d_test = date(2026, 10, 5)
    for d, cid in ((d_train, "CT"), (d_test, "CE")):
        add_settlement(session, d, 70.0)
        add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
        add_snapshot(session, cid, d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.60)

    out = run(
        min_favorite_probs=[0.0],
        min_train_days=3,
        split_date=date(2026, 10, 1),
        session=session,
    )

    assert out["split_date"] == "2026-10-01"
    rep = out["by_threshold"][0]
    assert rep["train"]["n_trades"] == 1
    assert rep["test"]["n_trades"] == 1


def test_contract_with_no_valid_price_produces_no_trade(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    # corrupt quote: yes_ask outside (0, 1) - mirrors execute_bet rejecting it
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 1.50)

    out = run(
        min_favorite_probs=[0.0], min_train_days=3, split_date=None, session=session
    )

    assert out["n_target_dates_traded"] == 0
    assert out["trades"] == []
