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
from datetime import date

from scipy.stats import norm

# Forecast error is seasonal (shoulder months like March run much noisier
# than e.g. September - see /api/calibration by_month), so a single
# year-round stdev overstates uncertainty in calm months and understates it
# in volatile ones. This window pools same-season history (wrapping across
# the year boundary) instead of blending all 12 months into one figure.
SEASONAL_WINDOW_DAYS = 45
MIN_SEASONAL_SAMPLES = 20  # fall back to the full-history fit below this


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


def _day_of_year_distance(a: date, b: date) -> int:
    """Circular distance in days between two dates' position in a 365-day
    year (ignores actual year, wraps Dec->Jan) - e.g. distance from
    Aug 19 to Aug 20 last year is 1, not ~365."""
    doy_a = a.timetuple().tm_yday
    doy_b = b.timetuple().tm_yday
    diff = abs(doy_a - doy_b)
    return min(diff, 365 - diff)


def fit_error_stats_seasonal(
    dated_errors: list[tuple[date, float]],
    target_date: date,
    window_days: int = SEASONAL_WINDOW_DAYS,
    min_samples: int = MIN_SEASONAL_SAMPLES,
) -> ErrorStats:
    """Same as fit_error_stats, but fit only on history within `window_days`
    of target_date's day-of-year (wrapping across year boundaries), so a
    summer prediction uses summer-appropriate error stats instead of a
    blend across all seasons. Falls back to the full history if the
    seasonal window doesn't have enough samples yet to fit reliably."""
    seasonal = [
        e for d, e in dated_errors if _day_of_year_distance(d, target_date) <= window_days
    ]
    if len(seasonal) >= min_samples:
        return fit_error_stats(seasonal)
    return fit_error_stats([e for _, e in dated_errors])


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
