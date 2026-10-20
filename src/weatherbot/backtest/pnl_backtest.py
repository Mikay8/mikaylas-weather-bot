"""Phase 3 P&L backtest, honest edition (rewritten 2026-10-19).

Replays the bot's ACTUAL trade decision (api/recommendations.py +
api/bot.py::run_bot_cycle, favorite/confidence-floor rule) against real
historical market_snapshots, forecasts and settlements, so the dollar
outcome of different min_favorite_prob settings can be evaluated.

Decision-time model
-------------------
The live bot runs on bot-cron's schedule; its first daily run is 08:10 UTC
(.railway/railway.ts) and it evaluates the same-day KXHIGHNY market. Every
target_date D therefore gets one simulated decision time: D 08:10 UTC. A
simulated decision may only use information with timestamp <= decision_time:

- quotes: the LATEST market_snapshots row per contract with
  timestamp <= decision_time (mirrors api/trading.py::execute_bet, which
  fills off the latest snapshot row at trade time);
- point forecast: the latest GFS_MOS row for D with
  forecast_time <= decision_time. A date with no such row is SKIPPED - it
  is never scored against a forecast issued after the trade would have
  fired (no lookahead, ever);
- error fit: walk-forward, only (forecast, settlement) pairs whose
  settlement date is strictly before D, using for each past date the
  forecast that was latest at or before *that* date's decision time.

One position per target_date: of all brackets evaluated for D, only the
single highest-favorite_prob contract is "traded", mirroring
skip_if_position_exists=true (bot.py iterates recs sorted by favorite_prob
descending and takes the first clearing the floor). Same-day brackets are
near-perfectly correlated bets on one number, so scoring all of them would
describe a portfolio the bot never runs.

What this fixes vs the previous version
---------------------------------------
- One position per day (see above). The old version took EVERY bracket
  clearing the floor - up to ~10 correlated same-day positions - so its
  trade count, win rate and PnL described a different strategy.
- Prices at the latest pre-decision quote. The old version priced each
  contract at its EARLIEST snapshot on record, which could predate the
  forecast it was scored against.
- Real lookahead guard. The old module docstring claimed "the
  forecast/market snapshot used is the latest one at or before a chosen
  decision_time" - no decision_time existed anywhere in run(). It does now,
  and the constraint is unit-tested (tests/test_pnl_backtest.py).
- Honest threshold validation: thresholds are selected on trades with
  target_date < SPLIT_DATE and evaluated on target_date >= SPLIT_DATE,
  with a multiple-comparison caveat, instead of crowning the max of 11
  in-sample sweeps on ~60 effectively-independent days.

Deliberately NOT reintroduced: the v1 edge-chasing rule (bet whichever
side has the bigger model_prob - market_prob edge). Commit 7afcd67 removed
it after a walk-forward backtest showed -$14 to -$50 per $1 staked at every
edge threshold tried: the model's miscalibration pulled it hardest toward
exactly the markets where it disagreed with the market *because it was
wrong*. Side selection stays favorite-vs-floor, exactly as the live bot
does it. edge/fee_adjusted_edge are still logged per trade for visibility
into how the chosen side compared to the market price; they do not gate.

Settlement source: the NWS CLI proxy (settlements table), same source the
live settle.py::resolve_pending_trades scores against. Kalshi has settled
KXHIGHNY on The Weather Company since 2026-08-14, so that proxy is exactly
where miscalibration would hide: every trade is flagged near_edge when the
settlement landed within 0.5F of a bracket edge, and PnL is reported with
and without those trades.

Fee model: kalshi_fee (the live taker formula), applied to
contracts = 1/price per $1 staked - mirroring execute_bet's
contracts = amount/price. (The old backtest charged the fee for a single
contract regardless of price; the difference is small because of the ceil,
but this matches the live accounting exactly.)
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import text

from weatherbot.api.settle import kalshi_fee, yes_wins
from weatherbot.backtest.model import (
    ErrorStats,
    bracket_probability,
    fit_error_stats_seasonal,
)
from weatherbot.db import get_session

DEFAULT_MIN_FAVORITE_PROBS = [
    0.5,
    0.6,
    0.7,
    0.72,
    0.74,
    0.76,
    0.78,
    0.8,
    0.85,
    0.9,
    0.95,
]
MIN_TRAIN_DAYS = 30

# bot-cron's first daily run (.railway/railway.ts). The live bot evaluates
# the same-day market at this time, so the simulated decision time is
# 08:10 UTC on each target_date.
DECISION_HOUR_UTC = 8
DECISION_MINUTE_UTC = 10

# Thresholds are selected on trades with target_date < SPLIT_DATE and
# evaluated on target_date >= SPLIT_DATE. Pass split_date=None to run() for
# a single full-sample report (with a stronger caveat - see below).
SPLIT_DATE = date(2026, 10, 1)

# A settlement within this distance (F) of a bracket edge is flagged
# near_edge - the NWS-CLI-vs-TWC settlement-source question lives here.
NEAR_EDGE_TOLERANCE_F = 0.5

MULTIPLE_COMPARISON_CAVEAT = (
    "Thresholds are chosen by sweeping N values, so the best test-set "
    "threshold is itself a selection over N tries: treat the maximum as "
    "optimistic, not as an expected return. The effective independent "
    "sample is the number of traded target dates (one position per day by "
    "construction), not the number of brackets evaluated."
)


@dataclass
class TradeResult:
    contract_id: str
    target_date: date
    side: str
    price: float
    favorite_prob: float  # model's stated probability for the side taken
    fee_adjusted_edge: float | None  # vs market price - logged, doesn't gate
    won: bool
    pnl: float  # per $1 staked
    near_edge: bool  # settlement within 0.5F of a bracket edge
    forecast_time: datetime  # GFS_MOS forecast_time actually used (<= decision_time)
    snapshot_time: (
        datetime  # market snapshot timestamp actually used (<= decision_time)
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["target_date"] = self.target_date.isoformat()
        d["forecast_time"] = self.forecast_time.isoformat()
        d["snapshot_time"] = self.snapshot_time.isoformat()
        return d


def summarize_trades(trades: list[TradeResult]) -> dict:
    n = len(trades)
    return {
        "n_trades": n,
        "win_rate": round(sum(t.won for t in trades) / n, 4) if n else None,
        "total_pnl_per_$1_staked": round(sum(t.pnl for t in trades), 4),
        "avg_pnl_per_$1_staked": round(sum(t.pnl for t in trades) / n, 4)
        if n
        else None,
    }


@dataclass
class ThresholdReport:
    min_favorite_prob: float
    trades: list[TradeResult] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "min_favorite_prob": self.min_favorite_prob,
            **summarize_trades(self.trades),
        }


def decision_time_for(target_date: date) -> datetime:
    """The simulated trade time for a target_date: 08:10 UTC that day,
    mirroring bot-cron's first daily run."""
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        DECISION_HOUR_UTC,
        DECISION_MINUTE_UTC,
        tzinfo=UTC,
    )


def _as_aware_utc(dt: datetime | str) -> datetime:
    # sqlite returns TIMESTAMP columns as plain strings; postgres returns
    # aware datetimes. Normalize both to aware UTC so <= comparisons
    # against decision_time are always well-defined.
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _as_date(d: date | str) -> date:
    # sqlite may return DATE columns as ISO strings; postgres returns dates.
    if isinstance(d, str):
        return date.fromisoformat(d)
    return d


def load_snapshots(session) -> dict[str, list[dict]]:
    """All market_snapshots rows with a usable quote, grouped by
    contract_id. Timestamp filtering is done in Python
    (select_decision_snapshot) so the <= decision_time comparison behaves
    identically on postgres and sqlite."""
    rows = session.execute(
        text(
            """
            SELECT contract_id, target_date, strike_type, bracket_low, bracket_high,
                   yes_bid, yes_ask, implied_prob, timestamp
            FROM market_snapshots
            WHERE target_date IS NOT NULL
              AND strike_type IS NOT NULL
              AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL
            """
        )
    ).fetchall()
    by_contract: dict[str, list[dict]] = {}
    for r in rows:
        m = dict(r._mapping)
        m["timestamp"] = _as_aware_utc(m["timestamp"])
        m["target_date"] = _as_date(m["target_date"])
        by_contract.setdefault(m["contract_id"], []).append(m)
    return by_contract


def select_decision_snapshot(
    snapshots: list[dict], decision_time: datetime
) -> dict | None:
    """The latest snapshot at or before decision_time - mirrors
    execute_bet, which fills off the latest snapshot row at trade time.
    Snapshots quoted after decision_time did not exist when the simulated
    trade fired and are never used."""
    eligible = [s for s in snapshots if s["timestamp"] <= decision_time]
    if not eligible:
        return None
    # deterministic tiebreak on contract_id (same contract_id here, but
    # keeps max() total in case of duplicate timestamps)
    return max(eligible, key=lambda s: (s["timestamp"], s["contract_id"]))


def load_gfs_mos_forecasts(session) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT target_date, predicted_high, forecast_time
            FROM forecasts
            WHERE model_source = 'GFS_MOS' AND predicted_high IS NOT NULL
            """
        )
    ).fetchall()
    out = []
    for r in rows:
        m = dict(r._mapping)
        m["forecast_time"] = _as_aware_utc(m["forecast_time"])
        m["target_date"] = _as_date(m["target_date"])
        out.append(m)
    return out


def forecast_for_date(
    forecasts: list[dict], target_date: date, decision_time: datetime
) -> tuple[float, datetime] | None:
    """Latest GFS_MOS forecast for target_date issued at or before
    decision_time. Returns None when no qualifying row exists - the date is
    then skipped outright. A forecast issued after decision_time must never
    inform the simulated trade (no lookahead, ever)."""
    eligible = [
        f
        for f in forecasts
        if f["target_date"] == target_date and f["forecast_time"] <= decision_time
    ]
    if not eligible:
        return None
    best = max(eligible, key=lambda f: f["forecast_time"])
    return float(best["predicted_high"]), best["forecast_time"]


def load_dated_errors(session) -> list[tuple[date, float, datetime]]:
    """(target_date, actual_high - predicted_high, forecast_time) pairs for
    every settled date with a GFS_MOS forecast. Uses the latest GFS_MOS row
    per target_date, mirroring what the live path feeds the model."""
    forecasts = load_gfs_mos_forecasts(session)
    latest: dict[date, dict] = {}
    for f in forecasts:
        d = f["target_date"]
        if d not in latest or f["forecast_time"] > latest[d]["forecast_time"]:
            latest[d] = f
    rows = session.execute(text("SELECT date, actual_high FROM settlements")).fetchall()
    out = []
    for r in rows:
        m = dict(r._mapping)
        d = _as_date(m["date"])
        f = latest.get(d)
        if f is None or m["actual_high"] is None:
            continue
        out.append(
            (
                d,
                float(m["actual_high"]) - float(f["predicted_high"]),
                f["forecast_time"],
            )
        )
    return out


def prior_errors_for(
    dated_errors: list[tuple[date, float, datetime]], target_date: date
) -> list[tuple[date, float]]:
    """Walk-forward error history for a simulated decision on target_date:
    settlement dates strictly before target_date, each scored against the
    forecast that was latest at or before *that* date's own decision time
    (a forecast issued after the simulated trade could not have informed
    the error the model was fit on)."""
    return [
        (d, e)
        for d, e, ft in dated_errors
        if d < target_date and ft <= decision_time_for(d)
    ]


def load_settlements(session) -> dict[date, float]:
    rows = session.execute(text("SELECT date, actual_high FROM settlements")).fetchall()
    return {
        _as_date(r._mapping["date"]): float(r._mapping["actual_high"]) for r in rows
    }


def near_bracket_edge(
    strike_type: str,
    bracket_low: float | None,
    bracket_high: float | None,
    actual_high: float,
) -> bool:
    """True when the settlement landed within NEAR_EDGE_TOLERANCE_F of a
    bracket edge - the NWS-CLI-vs-TWC settlement-source question lives
    exactly in these trades."""
    tol = NEAR_EDGE_TOLERANCE_F
    if strike_type == "greater":
        return abs(actual_high - float(bracket_low)) <= tol
    if strike_type == "less":
        return abs(actual_high - float(bracket_high)) <= tol
    if strike_type == "between":
        return (
            abs(actual_high - float(bracket_low)) <= tol
            or abs(actual_high - float(bracket_high)) <= tol
        )
    raise ValueError(f"Unknown strike_type: {strike_type}")


def simulate_trade(
    market: dict,
    stats: ErrorStats,
    predicted_high: float,
    forecast_time: datetime,
    actual_high: float,
) -> TradeResult | None:
    """One contract's simulated fill at the decision snapshot.

    Side = the model's favorite (whichever of YES/NO it rates more likely),
    exactly as recommendations.py does - NOT whichever side has the bigger
    edge over the market price (see module docstring for why the v1
    edge-chasing rule stays retired). Price crosses the spread like the
    live paper fill: yes_ask for YES, 1 - yes_bid for NO. Returns None when
    no valid price exists (mirrors execute_bet rejecting the bet)."""
    model_prob = bracket_probability(
        predicted_high,
        stats,
        market["strike_type"],
        float(market["bracket_low"]) if market["bracket_low"] is not None else None,
        float(market["bracket_high"]) if market["bracket_high"] is not None else None,
    )
    market_prob = (
        float(market["implied_prob"]) if market["implied_prob"] is not None else None
    )
    if model_prob >= 0.5:
        side, price, favorite_prob = "yes", market["yes_ask"], model_prob
    else:
        # Decimal(str(...)): yes_bid may arrive as float (sqlite) or Decimal
        # (postgres); Decimal("1") - float would raise TypeError.
        bid = market["yes_bid"]
        price = Decimal(1) - Decimal(str(bid)) if bid is not None else None
        favorite_prob = 1 - model_prob
        side = "no"

    if price is None or not (0 < price < 1):
        return None

    # edge/fee_adjusted_edge are logged for visibility into how the chosen
    # side compared to the market price; they do not gate the trade.
    # NOTE: fee_adjusted_edge subtracts a per-contract dollar fee from a
    # probability - dimensionally loose, kept only as a rough diagnostic.
    edge = (model_prob - market_prob) if market_prob is not None else None
    if side == "no" and edge is not None:
        edge = -edge

    price_dec = Decimal(str(price))
    contracts = Decimal(1) / price_dec  # per $1 staked, as in execute_bet
    fee = kalshi_fee(contracts, price_dec)
    fee_adjusted_edge = edge - float(fee) if edge is not None else None

    won = yes_wins(
        market["strike_type"],
        float(market["bracket_low"]) if market["bracket_low"] is not None else None,
        float(market["bracket_high"]) if market["bracket_high"] is not None else None,
        actual_high,
    )
    if side == "no":
        won = not won
    payout = contracts * Decimal("1.00") if won else Decimal("0.00")
    pnl = float(payout - Decimal(1) - fee)  # pnl per $1 staked

    return TradeResult(
        contract_id=market["contract_id"],
        target_date=market["target_date"],
        side=side,
        price=float(price),
        favorite_prob=favorite_prob,
        fee_adjusted_edge=fee_adjusted_edge,
        won=won,
        pnl=pnl,
        near_edge=near_bracket_edge(
            market["strike_type"],
            float(market["bracket_low"]) if market["bracket_low"] is not None else None,
            float(market["bracket_high"])
            if market["bracket_high"] is not None
            else None,
            actual_high,
        ),
        forecast_time=forecast_time,
        snapshot_time=market["timestamp"],
    )


def run(
    min_favorite_probs: list[float] = DEFAULT_MIN_FAVORITE_PROBS,
    min_train_days: int = MIN_TRAIN_DAYS,
    split_date: date | None = SPLIT_DATE,
    session=None,
) -> dict:
    """Replay the bot's decision over history, honestly.

    For each settled target_date: build the 08:10 UTC decision from only
    pre-decision quotes and forecasts, fit error stats walk-forward, and
    take at most the single highest-favorite_prob contract (mirrors
    skip_if_position_exists=true). Thresholds are then swept over those
    per-date trades, reported separately for target_date < split_date
    (train: where a threshold would be selected) and >= split_date (test:
    where it is evaluated). Pass split_date=None for a single full-sample
    report.
    """
    close_session = session is None
    if close_session:
        session = get_session()
    try:
        snapshots = load_snapshots(session)
        forecasts = load_gfs_mos_forecasts(session)
        dated_errors = load_dated_errors(session)
        settlements = load_settlements(session)

        dates_with_snaps = {
            s["target_date"] for group in snapshots.values() for s in group
        }
        target_dates = sorted(d for d in settlements if d in dates_with_snaps)

        all_trades: list[TradeResult] = []
        skipped_no_snapshot = 0
        skipped_no_forecast = 0
        skipped_insufficient_history = 0

        for target_date in target_dates:
            decision_time = decision_time_for(target_date)
            actual_high = settlements[target_date]

            day_snaps = []
            for group in snapshots.values():
                snap = select_decision_snapshot(
                    [s for s in group if s["target_date"] == target_date], decision_time
                )
                if snap is not None:
                    day_snaps.append(snap)
            if not day_snaps:
                skipped_no_snapshot += 1
                continue

            fc = forecast_for_date(forecasts, target_date, decision_time)
            if fc is None:
                skipped_no_forecast += 1
                continue
            predicted_high, forecast_time = fc

            # Walk-forward: only settlements strictly before target_date.
            prior_errors = prior_errors_for(dated_errors, target_date)
            if len(prior_errors) < min_train_days:
                skipped_insufficient_history += 1
                continue

            stats = fit_error_stats_seasonal(prior_errors, target_date)
            candidates = []
            for snap in day_snaps:
                trade = simulate_trade(
                    snap, stats, predicted_high, forecast_time, actual_high
                )
                if trade is not None:
                    candidates.append(trade)
            if not candidates:
                continue
            # One position per day: the highest-favorite_prob contract,
            # mirroring bot.py's skip_if_position_exists + favorite_prob sort.
            # Deterministic tiebreak on contract_id.
            all_trades.append(
                max(candidates, key=lambda t: (t.favorite_prob, t.contract_id))
            )

        by_threshold = []
        for thr in min_favorite_probs:
            qualified = [t for t in all_trades if t.favorite_prob >= thr]
            train = [
                t for t in qualified if split_date is None or t.target_date < split_date
            ]
            test = [
                t
                for t in qualified
                if split_date is not None and t.target_date >= split_date
            ]
            by_threshold.append(
                {
                    "min_favorite_prob": thr,
                    "train": ThresholdReport(thr, train).summary(),
                    "test": ThresholdReport(thr, test).summary(),
                }
            )

        away_from_edge = [t for t in all_trades if not t.near_edge]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "decision_time_rule": (
                f"{DECISION_HOUR_UTC:02d}:{DECISION_MINUTE_UTC:02d} UTC on each "
                "target_date (mirrors bot-cron's first daily run)"
            ),
            "split_date": split_date.isoformat() if split_date else None,
            "n_target_dates_traded": len(all_trades),
            "n_target_dates_skipped_no_snapshot": skipped_no_snapshot,
            "n_target_dates_skipped_no_forecast": skipped_no_forecast,
            "n_target_dates_skipped_insufficient_history": skipped_insufficient_history,
            "by_threshold": by_threshold,
            "near_edge_analysis": {
                "n_near_edge_trades": sum(t.near_edge for t in all_trades),
                "all_trades": summarize_trades(all_trades),
                "excluding_near_edge_trades": summarize_trades(away_from_edge),
            },
            "multiple_comparison_caveat": MULTIPLE_COMPARISON_CAVEAT,
            "trades": [t.to_dict() for t in all_trades],
        }
    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2, default=str))
