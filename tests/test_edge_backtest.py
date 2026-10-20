"""Unit tests for the capped-edge backtest (edge_backtest.py).

All fixtures are synthetic and run against an in-memory SQLite database -
no DATABASE_URL, no network. Each test pins one semantic of the new rule:

 1. fee units: fee_per_dollar is the taker fee on the position a $1 stake
    actually buys (contracts = 1/price), NOT v1's single-contract fee
 2. fee_adjusted_edge below E -> no trade
 3. price above the cap P -> no trade (same candidate trades under P=0.99)
 4. day sigma above the risk cap S -> no trade (trades under S=99.0)
 5. at most one position per day: the highest-fee_adjusted_edge candidate
 6. a forecast issued after decision time is never usable (no lookahead)
 7. default grid is 6 x 5 x 4 = 120 cells with exactly one v1 reference
    cell (E=0.03, P=0.99, S=99.0) and a multiple-comparison caveat
"""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from weatherbot.api.settle import kalshi_fee
from weatherbot.backtest.edge_backtest import (
    build_candidates,
    fee_adjusted_edge,
    fee_per_dollar,
    passes_gates,
    run,
    select_candidate,
)
from weatherbot.backtest.model import STDEV_INFLATION_FACTOR, ErrorStats

# stdev of the standard seeded history below: errors alternate +/-1 over
# 6 days -> bias 0, sample variance 6/5 = 1.2, seasonal fallback fit
# (n < MIN_SEASONAL_SAMPLES=20) inflates by STDEV_INFLATION_FACTOR.
SEEDED_STDEV = math.sqrt(1.2) * STDEV_INFLATION_FACTOR  # ~= 1.194


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
    low: float | None,
    high: float | None,
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


def seed_error_history(session, first: date, n: int, magnitude: float = 1.0):
    """n past dates, actual 70F, alternating +/-magnitude GFS_MOS errors.

    magnitude=1.0 -> bias 0, stdev sqrt(1.2) * 1.09 ~= 1.19 (calm day).
    magnitude=3.0 -> bias 0, stdev sqrt(10.8) * 1.09 ~= 3.58 (risky day).
    """
    for i in range(n):
        d = first + timedelta(days=i)
        err = magnitude if i % 2 == 0 else -magnitude
        add_settlement(session, d, 70.0)
        add_forecast(session, d, 70.0 - err, utc_dt(d, 0, 0))


def seed_calm_day(session, d: date):
    """A tradeable day on the calm seeded history: forecast 70, actual 70,
    one 'between 70-71' contract quoted 0.40/0.45. Its YES candidate has
    fee_adjusted_edge ~= 0.068 (model prob ~= 0.558 - 0.45 - 0.04 fee)."""
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.45)


def only_cell(out: dict) -> dict:
    assert len(out["cells"]) == 1
    return out["cells"][0]


# --- 1. fee units -------------------------------------------------------


def test_fee_per_dollar_is_fee_on_the_dollar_position_not_one_contract():
    # $1 at price 0.50 buys 2 contracts; taker fee =
    # ceil(0.07 * 2 * 0.5 * 0.5 * 100)/100 = ceil(3.5)/100 = 0.04.
    assert fee_per_dollar(Decimal("0.50")) == Decimal("0.04")
    # v1's bug: fee on ONE contract = ceil(1.75)/100 = 0.02 - half the
    # real fee at this price, and ~7x too small at price 0.10.
    assert kalshi_fee(Decimal(1), Decimal("0.50")) == Decimal("0.02")
    assert fee_per_dollar(Decimal("0.50")) != kalshi_fee(Decimal(1), Decimal("0.50"))
    # $1 at price 0.10 buys 10 contracts:
    # ceil(0.07 * 10 * 0.1 * 0.9 * 100)/100 = ceil(6.3)/100 = 0.07.
    assert fee_per_dollar(Decimal("0.10")) == Decimal("0.07")


def test_fee_adjusted_edge_worked_example():
    # model says 0.70, price 0.50, fee on the $1 position is 0.04:
    # 0.70 - 0.50 - 0.04 = 0.16.
    assert fee_adjusted_edge(0.70, Decimal("0.50")) == pytest.approx(0.16)


# --- 2. edge gate -------------------------------------------------------


def test_edge_below_threshold_produces_no_trade(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    seed_calm_day(session, d)

    out = run(
        edge_thresholds=[0.05, 0.15],
        price_caps=[0.99],
        sigma_caps=[99.0],
        min_train_days=3,
        split_date=None,
        session=session,
    )

    by_e = {c["edge_threshold"]: c for c in out["cells"]}
    # best candidate's fee_adjusted_edge ~= 0.068: clears 0.05, not 0.15
    assert by_e[0.05]["train"]["n_trades"] == 1
    assert by_e[0.15]["train"]["n_trades"] == 0


def test_select_candidate_respects_all_gates_at_boundaries():
    stats = ErrorStats(bias=0.0, stdev=SEEDED_STDEV, n=6)
    market = {
        "contract_id": "C1",
        "target_date": date(2026, 10, 5),
        "timestamp": utc_dt(date(2026, 10, 5), 7, 0),
        "strike_type": "between",
        "bracket_low": 70,
        "bracket_high": 71,
        "yes_bid": 0.40,
        "yes_ask": 0.45,
        "implied_prob": None,
    }
    candidates = build_candidates(market, stats, 70.0, utc_dt(date(2026, 10, 5)), 70.0)
    yes = next(c for c in candidates if c.side == "yes")
    # gates are inclusive: edge == E, price == P, sigma == S all pass
    assert passes_gates(yes, yes.fee_adjusted_edge, yes.price, yes.sigma)
    assert not passes_gates(yes, yes.fee_adjusted_edge + 0.001, yes.price, yes.sigma)
    assert not passes_gates(yes, 0.0, yes.price - 0.01, yes.sigma)
    assert not passes_gates(yes, 0.0, yes.price, yes.sigma - 0.01)
    assert select_candidate(candidates, 99.0, 0.99, 99.0) is None


# --- 3. price cap -------------------------------------------------------


def test_price_above_cap_produces_no_trade(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    # 'greater 65' with forecast 70: model prob ~= 0.9999, quoted 0.93/0.95,
    # so the YES candidate has fee_adjusted_edge ~= 0.04 at price 0.95 -
    # it clears the edge gate and trades ONLY if the cap allows 0.95.
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "greater", 65, None, 0.93, 0.95)

    out = run(
        edge_thresholds=[0.03],
        price_caps=[0.90, 0.99],
        sigma_caps=[99.0],
        min_train_days=3,
        split_date=None,
        session=session,
    )

    by_p = {c["price_cap"]: c for c in out["cells"]}
    assert by_p[0.90]["train"]["n_trades"] == 0
    assert by_p[0.99]["train"]["n_trades"] == 1


# --- 4. risk (sigma) cap -------------------------------------------------


def test_sigma_above_cap_produces_no_trade(session):
    # wide seeded history: day sigma ~= sqrt(10.8) * 1.09 ~= 3.58
    seed_error_history(session, date(2026, 9, 20), 6, magnitude=3.0)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
    # wide 'between 68-72' bracket quoted cheap: YES prob ~= 0.51 under
    # the wide fit, edge ~= 0.51 - 0.25 - 0.06 fee ~= 0.20 - passes the
    # edge and price gates whenever the sigma cap lets the day trade.
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 68, 72, 0.20, 0.25)

    out = run(
        edge_thresholds=[0.03],
        price_caps=[0.99],
        sigma_caps=[3.0, 99.0],
        min_train_days=3,
        split_date=None,
        session=session,
    )

    by_s = {c["sigma_cap"]: c for c in out["cells"]}
    assert by_s[3.0]["train"]["n_trades"] == 0
    assert by_s[99.0]["train"]["n_trades"] == 1


# --- 5. one position per day, highest edge wins --------------------------


def test_one_position_per_day_highest_edge_candidate(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    for d in (date(2026, 10, 5), date(2026, 10, 6)):
        add_settlement(session, d, 70.0)
        add_forecast(session, d, 70.0, utc_dt(d, 0, 0))
        # C1 YES fee_adjusted_edge ~= 0.068 (see seed_calm_day math)
        add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.45)
        # C2 'less than 72' YES: prob = P(actual <= 71.5) ~= 0.896, quoted
        # 0.80/0.84 -> edge ~= 0.896 - 0.84 - 0.02 fee ~= 0.036. Passes
        # E=0.03 too, but C1's edge is bigger, so C1 must win the day.
        add_snapshot(session, "C2", d, utc_dt(d, 7, 0), "less", None, 72, 0.80, 0.84)

    out = run(
        edge_thresholds=[0.03],
        price_caps=[0.99],
        sigma_caps=[99.0],
        min_train_days=3,
        split_date=None,
        session=session,
    )

    cell = only_cell(out)
    assert cell["is_v1_reference"] is True
    assert cell["train"]["n_trades"] == 2  # one per day, two days
    trades = out["v1_reference_trades"]
    assert len(trades) == 2
    assert {t["target_date"] for t in trades} == {"2026-10-05", "2026-10-06"}
    assert all(t["contract_id"] == "C1" and t["side"] == "yes" for t in trades)


# --- 6. no lookahead ------------------------------------------------------


def test_forecast_issued_after_decision_time_is_not_usable(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    d = date(2026, 10, 5)
    add_settlement(session, d, 70.0)
    # the only GFS_MOS row was issued at 09:00, after the 08:10 decision
    add_forecast(session, d, 70.0, utc_dt(d, 9, 0))
    add_snapshot(session, "C1", d, utc_dt(d, 7, 0), "between", 70, 71, 0.40, 0.45)

    out = run(
        edge_thresholds=[0.03],
        price_caps=[0.99],
        sigma_caps=[99.0],
        min_train_days=3,
        split_date=None,
        session=session,
    )

    assert out["n_target_dates_skipped_no_forecast"] == 1
    assert out["n_target_dates_evaluated"] == 0
    assert only_cell(out)["train"]["n_trades"] == 0
    assert out["v1_reference_trades"] == []


# --- 7. grid shape --------------------------------------------------------


def test_default_grid_is_120_cells_with_one_v1_reference(session):
    seed_error_history(session, date(2026, 9, 20), 6)
    seed_calm_day(session, date(2026, 10, 5))

    out = run(min_train_days=3, split_date=date(2026, 10, 1), session=session)

    assert out["grid"]["n_cells"] == 120
    assert len(out["cells"]) == 120
    refs = [c for c in out["cells"] if c["is_v1_reference"]]
    assert len(refs) == 1
    assert (
        refs[0]["edge_threshold"],
        refs[0]["price_cap"],
        refs[0]["sigma_cap"],
    ) == (0.03, 0.99, 99.0)
    assert "120" in out["multiple_comparison_caveat"]
    # every cell carries the near-edge split alongside train/test
    for cell in out["cells"]:
        assert "n_near_edge_trades" in cell["near_edge_analysis"]
        assert "train" in cell and "test" in cell
