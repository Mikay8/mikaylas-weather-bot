"""Phase 2 probability model: converts a point forecast into a probability
distribution over Kalshi's bracket structure.

v1 approach (per the build spec): normal distribution around predicted_high,
with the mean shift (bias) and stdev derived empirically from historical
forecast error (actual_high - predicted_high) rather than assumed. This is
the calibration the NWS/GFS_MOS ingest modules deferred to "Phase 2/3".

Bias/stdev are fit only on GFS_MOS history (the one source with a full year
of paired forecast/settlement data). Applied to whichever forecast row is
most recent for a target_date regardless of model_source — a documented v1
simplification, since NWS and GFS_MOS next-day point forecasts for the same
station track closely and NWS has no independent error history yet.
"""

from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class ErrorStats:
    bias: float  # mean(actual - predicted); add to predicted_high to de-bias
    stdev: float  # stdev(actual - predicted)
    n: int


def fit_error_stats(errors: list[float]) -> ErrorStats:
    """errors = [actual_high - predicted_high, ...] from historical paired data."""
    n = len(errors)
    if n < 2:
        raise ValueError("Need at least 2 historical errors to fit stdev")
    mean = sum(errors) / n
    var = sum((e - mean) ** 2 for e in errors) / (n - 1)
    return ErrorStats(bias=mean, stdev=var**0.5, n=n)


def bracket_probability(
    predicted_high: float,
    stats: ErrorStats,
    strike_type: str,
    bracket_low: float | None,
    bracket_high: float | None,
) -> float:
    """P(actual_high falls in this Kalshi bracket) under
    Normal(predicted_high + bias, stdev), matching settle.py's yes_wins
    semantics: 'greater' wins if actual > bracket_low, 'less' wins if
    actual < bracket_high, 'between' wins if bracket_low <= actual <= bracket_high.
    """
    mean = predicted_high + stats.bias
    sd = stats.stdev
    if sd <= 0:
        raise ValueError("stdev must be positive")

    if strike_type == "greater":
        return float(norm.sf(bracket_low, loc=mean, scale=sd))
    if strike_type == "less":
        return float(norm.cdf(bracket_high, loc=mean, scale=sd))
    if strike_type == "between":
        return float(
            norm.cdf(bracket_high, loc=mean, scale=sd)
            - norm.cdf(bracket_low, loc=mean, scale=sd)
        )
    raise ValueError(f"Unknown strike_type: {strike_type}")
