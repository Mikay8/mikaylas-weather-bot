"""Phase 2 calibration backtest: validates the probability model (model.py)
against real historical settlements using walk-forward fitting — bias/stdev
for predicting day N are fit only on days strictly before N, so this never
uses information that wouldn't have been available at the time.

No historical Kalshi market prices exist yet (see market_snapshots — only
a couple hours of live snapshots as of this writing), so this scores model
calibration only (Brier score, coverage, MAE), not fee-adjusted P&L. Once
market-cron accumulates real bracket price history, a market-edge backtest
can be added on top of this.
"""

from dataclasses import dataclass, field
from datetime import date

from scipy.stats import norm
from sqlalchemy import text

from weatherbot.backtest.model import ErrorStats, fit_error_stats_seasonal
from weatherbot.db import get_session

MIN_TRAIN_DAYS = 30


@dataclass
class DayResult:
    target_date: date
    predicted_high: float
    actual_high: float
    error: float  # actual - predicted
    bias_used: float
    stdev_used: float
    # Brier score for a fixed +/-2F "would you buy YES on actual > predicted-1"
    # style bracket is arbitrary without real market brackets, so we instead
    # score calibration directly: was actual_high within the model's stated
    # 68%/90% central interval for that day.
    within_68: bool
    within_90: bool


@dataclass
class CalibrationReport:
    results: list[DayResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def mae(self) -> float:
        return sum(abs(r.error) for r in self.results) / self.n

    @property
    def bias(self) -> float:
        return sum(r.error for r in self.results) / self.n

    @property
    def coverage_68(self) -> float:
        return sum(r.within_68 for r in self.results) / self.n

    @property
    def coverage_90(self) -> float:
        return sum(r.within_90 for r in self.results) / self.n

    def by_month(self) -> dict[str, "CalibrationReport"]:
        out: dict[str, list[DayResult]] = {}
        for r in self.results:
            key = r.target_date.strftime("%Y-%m")
            out.setdefault(key, []).append(r)
        return {k: CalibrationReport(v) for k, v in sorted(out.items())}

    def summary(self) -> dict:
        return {
            "n": self.n,
            "mae": round(self.mae, 3),
            "bias": round(self.bias, 3),
            "coverage_68": round(self.coverage_68, 3),
            "coverage_90": round(self.coverage_90, 3),
        }


def load_paired_history(model_source: str = "GFS_MOS") -> list[tuple[date, float, float]]:
    """Returns [(target_date, predicted_high, actual_high), ...] sorted by date."""
    session = get_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT f.target_date, f.predicted_high, s.actual_high
                FROM forecasts f
                JOIN settlements s
                  ON s.date = f.target_date AND s.station = f.station
                WHERE f.model_source = :model_source
                ORDER BY f.target_date
                """
            ),
            {"model_source": model_source},
        ).fetchall()
        return [(r.target_date, float(r.predicted_high), float(r.actual_high)) for r in rows]
    finally:
        session.close()


def run_walk_forward(
    history: list[tuple[date, float, float]], min_train_days: int = MIN_TRAIN_DAYS
) -> CalibrationReport:
    """For each day past min_train_days, fit ErrorStats on all strictly-prior
    days (seasonally weighted, matching the live recommendation engine) and
    score that day's prediction against it — no lookahead."""
    report = CalibrationReport()
    dated_errors_so_far: list[tuple[date, float]] = []

    for target_date, predicted_high, actual_high in history:
        if len(dated_errors_so_far) >= min_train_days:
            stats: ErrorStats = fit_error_stats_seasonal(dated_errors_so_far, target_date)
            mean = predicted_high + stats.bias
            sd = stats.stdev
            lo68, hi68 = norm.interval(0.68, loc=mean, scale=sd)
            lo90, hi90 = norm.interval(0.90, loc=mean, scale=sd)
            error = actual_high - predicted_high
            report.results.append(
                DayResult(
                    target_date=target_date,
                    predicted_high=predicted_high,
                    actual_high=actual_high,
                    error=error,
                    bias_used=stats.bias,
                    stdev_used=stats.stdev,
                    within_68=lo68 <= actual_high <= hi68,
                    within_90=lo90 <= actual_high <= hi90,
                )
            )

        dated_errors_so_far.append((target_date, actual_high - predicted_high))

    return report


def run(model_source: str = "GFS_MOS", min_train_days: int = MIN_TRAIN_DAYS) -> dict:
    history = load_paired_history(model_source)
    report = run_walk_forward(history, min_train_days)
    return {
        "overall": report.summary(),
        "by_month": {k: v.summary() for k, v in report.by_month().items()},
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2, default=str))
