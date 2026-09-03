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

v1.1: fit_error_stats's sample stdev alone was underdispersed - walk-forward
scoring (calibration.py) measured actual 68%/90% coverage at 67.6%/89.1%
against nominal targets of 68%/90% overall, but far worse in specific
months (e.g. 2026-08: 58.1%, 2026-02: 60.7%), and a wider or narrower
seasonal window doesn't fix it (tested window_days 15-120 - all land within
0.68-0.70 coverage_68, see conversation history). The standardized error
(actual - predicted - bias) / stdev has empirical stdev ~1.09 instead of
the ~1.0 a correctly-dispersed model would have, i.e. the fitted stdev
itself is consistently ~9% too narrow. STDEV_INFLATION_FACTOR corrects
that multiplicatively. It's a fixed constant rather than refit per call
because a walk-forward split-half test (first half fits the factor, second
half is scored out-of-sample against it) confirmed it generalizes: coverage
went from 69.5% to 74.2% out-of-sample, both closer to and on the correct
side of the 68% target than the uninflated model. Revisit this number
periodically via calibration.py once enough new settlements accumulate to
refit it (see fit_stdev_inflation_factor below).
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

# See v1.1 note above - corrects fit_error_stats's sample stdev being
# systematically too narrow. Fit once on ~a year of GFS_MOS walk-forward
# history via fit_stdev_inflation_factor(); not refit on every call since
# that would need its own walk-forward split to avoid overfitting the same
# data it's correcting.
STDEV_INFLATION_FACTOR = 1.09


@dataclass(frozen=True)
class ErrorStats:
    bias: float  # mean(actual - predicted); add to predicted_high to de-bias
    stdev: float  # stdev(actual - predicted), already inflation-corrected
    n: int


def fit_error_stats(errors: list[float], inflation_factor: float = STDEV_INFLATION_FACTOR) -> ErrorStats:
    """errors = [actual_high - predicted_high, ...] from historical paired data."""
    n = len(errors)
    if n < 2:
        raise ValueError("Need at least 2 historical errors to fit stdev")
    mean = sum(errors) / n
    var = sum((e - mean) ** 2 for e in errors) / (n - 1)
    return ErrorStats(bias=mean, stdev=(var**0.5) * inflation_factor, n=n)


def fit_stdev_inflation_factor(dated_errors: list[tuple[date, float]]) -> float:
    """Refit STDEV_INFLATION_FACTOR from scratch: the stdev of standardized
    errors (actual - predicted - bias) / stdev under a walk-forward seasonal
    fit with no inflation applied. A correctly-dispersed model has this at
    1.0; >1 means the raw fit is underdispersed (too confident) by that
    multiple. Intended to be re-run periodically (e.g. from a notebook or
    calibration.py extension) as new settlements accumulate, not called
    from bracket_probability's hot path - see the v1.1 module docstring
    for why this isn't just refit on every prediction."""
    sorted_errors = sorted(dated_errors, key=lambda de: de[0])
    z_scores = []
    errors_so_far: list[tuple[date, float]] = []
    for target_date, error in sorted_errors:
        if len(errors_so_far) >= MIN_SEASONAL_SAMPLES:
            stats = fit_error_stats_seasonal(errors_so_far, target_date, inflation_factor=1.0)
            z_scores.append(error / stats.stdev)
        errors_so_far.append((target_date, error))

    n = len(z_scores)
    if n < 2:
        raise ValueError("Need at least 2 walk-forward z-scores to fit an inflation factor")
    mean_z = sum(z_scores) / n
    var_z = sum((z - mean_z) ** 2 for z in z_scores) / (n - 1)
    return var_z**0.5


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
    inflation_factor: float = STDEV_INFLATION_FACTOR,
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
        return fit_error_stats(seasonal, inflation_factor=inflation_factor)
    return fit_error_stats([e for _, e in dated_errors], inflation_factor=inflation_factor)


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
