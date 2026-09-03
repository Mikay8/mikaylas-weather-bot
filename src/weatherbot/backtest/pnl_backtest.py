"""Phase 3 P&L backtest: replays the bot's actual trade decision (recommendations.py
+ bot.py's edge-threshold gate) against real historical market_snapshots and
settlements, so the actual dollar outcome of different edge_threshold settings
can be evaluated - not just forecast calibration (calibration.py) or live-only
recommendations (recommendations.py).

Walk-forward like calibration.py: for a market closing on target_date, the
model's bias/stdev correction is fit only on settlements strictly before
target_date, and the forecast/market snapshot used is the latest one at or
before a chosen decision_time - never information from after the trade would
have been placed.

Deliberately out of scope for v1 (see recommendations.py / bot.py for the
live equivalents, not replayed here):
  - forecast-source-agreement gating (get_forecast_agreement) - live-query
    only, and market_snapshots history is too short yet for this to bind.
  - forecast staleness gating (is_forecast_stale) - same reason.
  - skip_if_position_exists - a single-position-per-day book-keeping rule,
    not a pricing/edge question.
Both are cheap to layer in once there's enough history for them to matter;
until then this scores the core edge-vs-price-vs-fee mechanics only, which is
the part a threshold setting actually controls.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from weatherbot.api.settle import kalshi_fee, yes_wins
from weatherbot.backtest.model import ErrorStats, bracket_probability, fit_error_stats_seasonal
from weatherbot.db import get_session

DEFAULT_THRESHOLDS = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]
MIN_TRAIN_DAYS = 30


@dataclass
class TradeResult:
    contract_id: str
    target_date: date
    side: str
    price: float
    fee_adjusted_edge: float
    won: bool
    pnl: float  # per $1 staked


@dataclass
class ThresholdReport:
    threshold: float
    trades: list[TradeResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float | None:
        return sum(t.won for t in self.trades) / self.n if self.n else None

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def avg_pnl_per_dollar(self) -> float | None:
        return self.total_pnl / self.n if self.n else None

    def summary(self) -> dict:
        return {
            "threshold": self.threshold,
            "n_trades": self.n,
            "win_rate": round(self.win_rate, 4) if self.win_rate is not None else None,
            "total_pnl_per_$1_staked": round(self.total_pnl, 4),
            "avg_pnl_per_$1_staked": round(self.avg_pnl_per_dollar, 4)
            if self.avg_pnl_per_dollar is not None
            else None,
        }


def load_market_days() -> list[dict]:
    """One row per (contract_id, target_date) market: the earliest snapshot
    with a valid yes_bid/yes_ask, so the backtest prices each market at the
    first quote seen for it rather than a look-ahead last/best price."""
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (ms.contract_id)
                    ms.contract_id, ms.target_date, ms.strike_type,
                    ms.bracket_low, ms.bracket_high, ms.yes_bid, ms.yes_ask,
                    ms.implied_prob, s.actual_high
                FROM market_snapshots ms
                JOIN settlements s ON s.date = ms.target_date
                WHERE ms.target_date IS NOT NULL
                  AND ms.strike_type IS NOT NULL
                  AND ms.yes_bid IS NOT NULL AND ms.yes_ask IS NOT NULL
                ORDER BY ms.contract_id, ms.timestamp ASC
                """
            )
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def load_forecast_for_date(session, target_date: date) -> float | None:
    row = session.execute(
        text(
            """
            SELECT predicted_high FROM forecasts
            WHERE target_date = :target_date AND model_source = 'GFS_MOS'
            ORDER BY forecast_time DESC
            LIMIT 1
            """
        ),
        {"target_date": target_date},
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def load_dated_errors(session) -> list[tuple[date, float]]:
    rows = session.execute(
        text(
            """
            SELECT f.target_date, s.actual_high - f.predicted_high AS error
            FROM forecasts f
            JOIN settlements s ON s.date = f.target_date
            WHERE f.model_source = 'GFS_MOS'
            ORDER BY f.target_date
            """
        )
    ).fetchall()
    return [(r.target_date, float(r.error)) for r in rows]


def simulate_trade(market: dict, stats: ErrorStats, predicted_high: float) -> TradeResult | None:
    model_prob = bracket_probability(
        predicted_high,
        stats,
        market["strike_type"],
        float(market["bracket_low"]) if market["bracket_low"] is not None else None,
        float(market["bracket_high"]) if market["bracket_high"] is not None else None,
    )
    market_prob = float(market["implied_prob"])
    edge_yes = model_prob - market_prob
    edge_no = (1 - model_prob) - (1 - market_prob)

    if edge_yes >= edge_no:
        side, edge, price = "yes", edge_yes, market["yes_ask"]
    else:
        side, edge, price = "no", edge_no, (
            Decimal("1") - market["yes_bid"] if market["yes_bid"] is not None else None
        )

    if price is None or not (0 < price < 1):
        return None

    price_dec = Decimal(str(price))
    fee = kalshi_fee(Decimal("1"), price_dec)
    fee_adjusted_edge = edge - float(fee)

    contracts = Decimal("1") / price_dec  # per $1 staked, matching execute_bet's amount/price
    won = yes_wins(
        market["strike_type"], market["bracket_low"], market["bracket_high"], market["actual_high"]
    )
    if side == "no":
        won = not won
    payout = contracts * Decimal("1.00") if won else Decimal("0.00")
    pnl = float(payout - Decimal("1") - fee)  # pnl per $1 staked

    return TradeResult(
        contract_id=market["contract_id"],
        target_date=market["target_date"],
        side=side,
        price=float(price),
        fee_adjusted_edge=fee_adjusted_edge,
        won=won,
        pnl=pnl,
    )


def run(thresholds: list[float] = DEFAULT_THRESHOLDS, min_train_days: int = MIN_TRAIN_DAYS) -> dict:
    session = get_session()
    try:
        dated_errors_all = load_dated_errors(session)
        markets = load_market_days()

        all_trades: list[TradeResult] = []
        skipped_no_forecast = 0
        skipped_insufficient_history = 0

        for market in sorted(markets, key=lambda m: m["target_date"]):
            target_date = market["target_date"]
            predicted_high = load_forecast_for_date(session, target_date)
            if predicted_high is None:
                skipped_no_forecast += 1
                continue

            # Walk-forward: only settlements strictly before target_date.
            prior_errors = [(d, e) for d, e in dated_errors_all if d < target_date]
            if len(prior_errors) < min_train_days:
                skipped_insufficient_history += 1
                continue

            stats = fit_error_stats_seasonal(prior_errors, target_date)
            trade = simulate_trade(market, stats, predicted_high)
            if trade is not None:
                all_trades.append(trade)

        reports = []
        for threshold in thresholds:
            report = ThresholdReport(
                threshold=threshold,
                trades=[t for t in all_trades if t.fee_adjusted_edge >= threshold],
            )
            reports.append(report.summary())

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_markets_considered": len(all_trades),
            "n_markets_skipped_no_forecast": skipped_no_forecast,
            "n_markets_skipped_insufficient_history": skipped_insufficient_history,
            "by_threshold": reports,
        }
    finally:
        session.close()


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2, default=str))
