"""Capped-edge backtest: the retired v1 edge rule, re-tested honestly.

Re-tests the v1 idea - bet whichever side (YES/NO) has the bigger
model-vs-market edge - with the two guards Mikayla asked for added on top:
a PRICE CAP (never pay more than P for a contract) and a RISK CAP (never
trade on a day whose walk-forward error stdev exceeds S). Everything else
about the replay is identical to pnl_backtest.py's honest discipline:

- one simulated decision per target_date at 08:10 UTC (bot-cron's first
  daily run);
- quotes: the LATEST market_snapshots row per contract with
  timestamp <= decision_time; YES fills at yes_ask, NO at 1 - yes_bid;
- forecast: the latest GFS_MOS row for the date with
  forecast_time <= decision_time; a date with no such row is SKIPPED
  (no lookahead, ever);
- error stats fit walk-forward on settlements strictly before the date;
- settlement scored against the NWS CLI proxy (settlements table), same
  as the live bot and pnl_backtest.py; near_edge flag on every trade;
- at most ONE position per target_date: the highest-fee_adjusted_edge
  candidate that passes all three gates.

The rule under test
-------------------
For every bracket of the target date, compute model_prob for YES via the
same bracket_probability path as the live model, and consider BOTH sides:

    YES: price = yes_ask,        model_prob_side = model_prob
    NO:  price = 1 - yes_bid,    model_prob_side = 1 - model_prob

    fee_adjusted_edge = model_prob_side - price - fee_per_dollar

where fee_per_dollar is the Kalshi taker fee on a $1 stake at that price:
kalshi_fee applied to contracts = 1/price (a $1 stake buys 1/price
contracts), so the fee is in dollars per $1 staked. v1's recommendations
code gated on a fee computed for ONE contract
(kalshi_fee(Decimal("1"), price)) regardless of the position the stake
actually buys - that units mismatch is deliberately NOT replicated here;
the fee now matches the position whose PnL is being scored (the same
contracts = 1/price accounting pnl_backtest.py's fills use).

Gates (ALL must pass for a candidate to be selectable):
    fee_adjusted_edge >= E   (edge threshold)
    price <= P               (price cap)
    day sigma <= S           (risk cap; sigma = the day's walk-forward
                              error stdev from fit_error_stats_seasonal)

Why re-test a rule that already lost: v1 (removed in commit 7afcd67) ran
with E = 0.03 on the buggy fee, NO price cap, NO risk filter, and was
evaluated by a backtest that also priced at the earliest snapshot and
took every qualifying bracket. It lost -$14 to -$50 per $1 staked at
every threshold tried. This module asks the narrower question Mikayla
posed: does the edge idea survive once it is replayed honestly AND the
two caps are on? The grid below sweeps E x P x S (120 cells, including a
labelled reference cell E=0.03 / P=0.99 / S=99.0 that replicates v1's
gating as closely as the honest replay allows). Read ONLY the test
split (target_date >= 2026-10-01) as evidence, and even that as a
selection over 120 cells - see the multiple-comparison caveat in the
output. A green in-sample cell is not a result.

Nothing here touches the live bot: pnl_backtest.py's favorite/floor rule
remains what bot-cron runs. This module only measures.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from weatherbot.api.settle import kalshi_fee, yes_wins
from weatherbot.backtest.model import (
    ErrorStats,
    bracket_probability,
    fit_error_stats_seasonal,
)
from weatherbot.backtest.pnl_backtest import (
    MIN_TRAIN_DAYS,
    SPLIT_DATE,
    decision_time_for,
    forecast_for_date,
    load_dated_errors,
    load_gfs_mos_forecasts,
    load_settlements,
    load_snapshots,
    near_bracket_edge,
    prior_errors_for,
    select_decision_snapshot,
    summarize_trades,
)
from weatherbot.db import get_session

EDGE_THRESHOLDS = [0.00, 0.03, 0.05, 0.08, 0.10, 0.15]
PRICE_CAPS = [0.70, 0.80, 0.85, 0.90, 0.99]
# 99.0 = effectively no risk filter (a day's sigma never gets near it) -
# the baseline the capped cells are compared against.
SIGMA_CAPS = [2.0, 2.5, 3.0, 99.0]

# The cell that replicates v1's gating (MIN_EDGE_THRESHOLD = 0.03, no
# price cap, no risk filter) under the honest replay, so the sweep can be
# sanity-checked against v1's known losing pattern.
V1_REFERENCE_CELL = (0.03, 0.99, 99.0)


@dataclass
class EdgeCandidate:
    contract_id: str
    target_date: date
    side: str  # "yes" | "no"
    price: float  # executable price for this side (crosses the spread)
    model_prob: float  # model's stated probability FOR THIS SIDE
    fee_adjusted_edge: float  # model_prob - price - fee_per_dollar
    sigma: float  # the day's walk-forward error stdev (the risk-cap input)
    won: bool
    pnl: float  # per $1 staked, exact live accounting (fee on 1/price contracts)
    near_edge: bool  # settlement within 0.5F of a bracket edge
    forecast_time: datetime  # GFS_MOS forecast_time actually used (<= decision_time)
    snapshot_time: datetime  # market snapshot actually used (<= decision_time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["target_date"] = self.target_date.isoformat()
        d["forecast_time"] = self.forecast_time.isoformat()
        d["snapshot_time"] = self.snapshot_time.isoformat()
        return d


def fee_per_dollar(price: Decimal) -> Decimal:
    """Kalshi taker fee, in dollars, on a $1 stake at `price`.

    A $1 stake buys contracts = 1/price (mirroring execute_bet's
    contracts = amount/price), so the fee is kalshi_fee evaluated on that
    position - NOT on a single contract. v1 gated on
    kalshi_fee(Decimal("1"), price), the fee for one contract no matter
    how many contracts the stake buys; at price 0.10 that understates the
    fee on a $1 position by ~7x (0.01 vs 0.07)."""
    return kalshi_fee(Decimal(1) / price, price)


def fee_adjusted_edge(model_prob_side: float, price: Decimal) -> float:
    """model_prob_side - price - fee_per_dollar, all per the module
    docstring: probability and price are per-contract, the fee is the
    dollars of taker fee a $1 stake pays at that price."""
    return model_prob_side - float(price) - float(fee_per_dollar(price))


def build_candidates(
    market: dict,
    stats: ErrorStats,
    predicted_high: float,
    forecast_time: datetime,
    actual_high: float,
) -> list[EdgeCandidate]:
    """Both tradable sides of one contract at the decision snapshot.

    Mirrors pnl_backtest.simulate_trade's pricing and PnL accounting
    exactly (cross the spread, contracts = 1/price per $1 staked, taker
    fee charged at settlement); the only difference is that BOTH sides
    are returned as candidates instead of just the model's favorite. A
    side whose price is missing or outside (0, 1) is dropped (mirrors
    execute_bet rejecting the bet); the other side may still qualify."""
    low = float(market["bracket_low"]) if market["bracket_low"] is not None else None
    high = float(market["bracket_high"]) if market["bracket_high"] is not None else None
    model_prob_yes = bracket_probability(
        predicted_high, stats, market["strike_type"], low, high
    )
    yes_won = yes_wins(market["strike_type"], low, high, actual_high)
    near_edge = near_bracket_edge(market["strike_type"], low, high, actual_high)

    # Decimal(str(...)): quotes may arrive as float (sqlite) or Decimal
    # (postgres); Decimal("1") - float would raise TypeError.
    ask = market["yes_ask"]
    bid = market["yes_bid"]
    side_inputs = [
        (
            "yes",
            model_prob_yes,
            Decimal(str(ask)) if ask is not None else None,
            yes_won,
        ),
        (
            "no",
            1 - model_prob_yes,
            Decimal(1) - Decimal(str(bid)) if bid is not None else None,
            not yes_won,
        ),
    ]

    candidates = []
    for side, prob_side, price, won in side_inputs:
        if price is None or not (0 < price < 1):
            continue
        contracts = Decimal(1) / price  # per $1 staked, as in execute_bet
        fee = kalshi_fee(contracts, price)
        payout = contracts * Decimal("1.00") if won else Decimal("0.00")
        candidates.append(
            EdgeCandidate(
                contract_id=market["contract_id"],
                target_date=market["target_date"],
                side=side,
                price=float(price),
                model_prob=prob_side,
                fee_adjusted_edge=fee_adjusted_edge(prob_side, price),
                sigma=stats.stdev,
                won=won,
                pnl=float(payout - Decimal(1) - fee),  # pnl per $1 staked
                near_edge=near_edge,
                forecast_time=forecast_time,
                snapshot_time=market["timestamp"],
            )
        )
    return candidates


def passes_gates(
    candidate: EdgeCandidate,
    edge_threshold: float,
    price_cap: float,
    sigma_cap: float,
) -> bool:
    """All three gates: enough fee-adjusted edge, price at or under the
    cap, and the day's model sigma at or under the risk cap."""
    return (
        candidate.fee_adjusted_edge >= edge_threshold
        and candidate.price <= price_cap
        and candidate.sigma <= sigma_cap
    )


def select_candidate(
    candidates: list[EdgeCandidate],
    edge_threshold: float,
    price_cap: float,
    sigma_cap: float,
) -> EdgeCandidate | None:
    """The day's single position under one grid cell: the highest
    fee_adjusted_edge among candidates passing all gates (deterministic
    tiebreak on contract_id, then side). None when nothing passes -
    the cell simply doesn't trade that day."""
    passing = [
        c for c in candidates if passes_gates(c, edge_threshold, price_cap, sigma_cap)
    ]
    if not passing:
        return None
    return max(passing, key=lambda c: (c.fee_adjusted_edge, c.contract_id, c.side))


@dataclass
class DayEvaluation:
    """Everything one target_date contributes, computed ONCE (quotes,
    forecast, walk-forward fit, both-side candidates) and then re-scored
    cheaply under every grid cell."""

    target_date: date
    candidates: list[EdgeCandidate] = field(default_factory=list)


def evaluate_days(
    session, min_train_days: int = MIN_TRAIN_DAYS
) -> tuple[list[DayEvaluation], dict]:
    """Replay the decision-time discipline of pnl_backtest.run() and
    return per-date candidate lists plus skip counters. Identical data
    discipline (same loaders, same <= decision_time constraints, same
    walk-forward fit); only candidate generation differs (both sides,
    edge-scored, instead of the favorite side only)."""
    snapshots = load_snapshots(session)
    forecasts = load_gfs_mos_forecasts(session)
    dated_errors = load_dated_errors(session)
    settlements = load_settlements(session)

    dates_with_snaps = {s["target_date"] for group in snapshots.values() for s in group}
    target_dates = sorted(d for d in settlements if d in dates_with_snaps)

    days: list[DayEvaluation] = []
    skipped = {
        "n_target_dates_skipped_no_snapshot": 0,
        "n_target_dates_skipped_no_forecast": 0,
        "n_target_dates_skipped_insufficient_history": 0,
    }
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
            skipped["n_target_dates_skipped_no_snapshot"] += 1
            continue

        fc = forecast_for_date(forecasts, target_date, decision_time)
        if fc is None:
            skipped["n_target_dates_skipped_no_forecast"] += 1
            continue
        predicted_high, forecast_time = fc

        # Walk-forward: only settlements strictly before target_date.
        prior_errors = prior_errors_for(dated_errors, target_date)
        if len(prior_errors) < min_train_days:
            skipped["n_target_dates_skipped_insufficient_history"] += 1
            continue

        stats = fit_error_stats_seasonal(prior_errors, target_date)
        candidates: list[EdgeCandidate] = []
        for snap in day_snaps:
            candidates.extend(
                build_candidates(
                    snap, stats, predicted_high, forecast_time, actual_high
                )
            )
        days.append(DayEvaluation(target_date=target_date, candidates=candidates))
    return days, skipped


def run(
    edge_thresholds: list[float] = EDGE_THRESHOLDS,
    price_caps: list[float] = PRICE_CAPS,
    sigma_caps: list[float] = SIGMA_CAPS,
    min_train_days: int = MIN_TRAIN_DAYS,
    split_date: date | None = SPLIT_DATE,
    session=None,
) -> dict:
    """Sweep the capped-edge rule over history under pnl_backtest's
    honest replay discipline.

    Each grid cell trades at most one position per target_date (the
    highest fee_adjusted_edge passing all three gates) and is reported
    separately for target_date < split_date (train) and >= split_date
    (test), with a near-edge split. Only test cells are evidence, and
    even they are selections over the whole grid - see
    multiple_comparison_caveat in the output.
    """
    close_session = session is None
    if close_session:
        session = get_session()
    try:
        days, skipped = evaluate_days(session, min_train_days=min_train_days)

        n_cells = len(edge_thresholds) * len(price_caps) * len(sigma_caps)
        cells = []
        reference_trades: list[dict] = []
        for e in edge_thresholds:
            for p in price_caps:
                for s in sigma_caps:
                    chosen = []
                    for day in days:
                        pick = select_candidate(day.candidates, e, p, s)
                        if pick is not None:
                            chosen.append(pick)
                    train = [
                        c
                        for c in chosen
                        if split_date is None or c.target_date < split_date
                    ]
                    test = [
                        c
                        for c in chosen
                        if split_date is not None and c.target_date >= split_date
                    ]
                    is_reference = (e, p, s) == V1_REFERENCE_CELL
                    cell = {
                        "edge_threshold": e,
                        "price_cap": p,
                        "sigma_cap": s,
                        "is_v1_reference": is_reference,
                        "train": summarize_trades(train),
                        "test": summarize_trades(test),
                        "near_edge_analysis": {
                            "n_near_edge_trades": sum(c.near_edge for c in chosen),
                            "train_excluding_near_edge": summarize_trades(
                                [c for c in train if not c.near_edge]
                            ),
                            "test_excluding_near_edge": summarize_trades(
                                [c for c in test if not c.near_edge]
                            ),
                        },
                    }
                    # Full trade lists for every cell would multiply the
                    # output by the grid size; keep them only for the v1
                    # reference cell, where they sanity-check the replay
                    # against v1's known losing pattern.
                    if is_reference:
                        reference_trades = [c.to_dict() for c in chosen]
                    cells.append(cell)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "rule": (
                "capped edge: bet the side (YES at yes_ask / NO at 1-yes_bid) "
                "with the highest fee_adjusted_edge = model_prob - price - "
                "fee_per_dollar (fee on contracts = 1/price per $1 staked), "
                "only when fee_adjusted_edge >= E, price <= P and the day's "
                "walk-forward sigma <= S; at most one position per target_date"
            ),
            "decision_time_rule": (
                "08:10 UTC on each target_date (mirrors bot-cron's first "
                "daily run; same replay discipline as pnl_backtest.py)"
            ),
            "split_date": split_date.isoformat() if split_date else None,
            "grid": {
                "edge_thresholds": edge_thresholds,
                "price_caps": price_caps,
                "sigma_caps": sigma_caps,
                "n_cells": n_cells,
                "v1_reference_cell": {
                    "edge_threshold": V1_REFERENCE_CELL[0],
                    "price_cap": V1_REFERENCE_CELL[1],
                    "sigma_cap": V1_REFERENCE_CELL[2],
                },
            },
            "n_target_dates_evaluated": len(days),
            **skipped,
            "cells": cells,
            "v1_reference_trades": reference_trades,
            "multiple_comparison_caveat": (
                f"This grid sweeps {n_cells} (edge_threshold, price_cap, "
                f"sigma_cap) combinations, so the best cell is a selection "
                f"over {n_cells} tries: treat its numbers as optimistic, "
                "not as an expected return. A positive TRAIN cell is not "
                "evidence of anything; only TEST cells (target_date >= "
                "split_date) count, and even they are selections over the "
                f"grid. The effective independent sample is the number of "
                "traded target dates (one position per day by "
                "construction), not the number of brackets evaluated."
            ),
        }
    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2, default=str))
