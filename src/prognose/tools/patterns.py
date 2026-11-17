"""Step 04: trend, seasonality and anomalies.

Trend comes from a robust STL decomposition. Seasonality and the noise scale come from a robust (Huber)
regression of the detrended series on seasonal dummies. Robust STL alone underestimates the noise scale
on short series and flags normal points; plain STL lets a spike leak into the same season of every year.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.seasonal import STL

from prognose.config import PatternConfig
from prognose.schemas import Anomaly, PatternResult

MIN_RELATIVE_SCALE = 1e-6
TREND_WINDOW_CYCLES = 3


def _strength(component: np.ndarray, residual: np.ndarray) -> float:
    """Hyndman's strength measure: 1 - Var(residual) / Var(component + residual), floored at 0."""
    total_variance = float(np.var(component + residual))
    if total_variance == 0.0:
        return 0.0
    return round(max(0.0, 1.0 - float(np.var(residual)) / total_variance), 4)


def _direction(slope: float, level: float, threshold: float) -> str:
    if abs(slope) / max(abs(level), 1e-9) < threshold:
        return "stabil"
    return "steigend" if slope > 0 else "fallend"


def _trend_window(period: int) -> int:
    """About three seasonal cycles, odd as STL requires; wide enough that the trend does not absorb noise."""
    window = TREND_WINDOW_CYCLES * period + 1
    return window if window % 2 == 1 else window + 1


def _seasonal_fit(
    detrended: np.ndarray, period: int, threshold: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (seasonal profile centred on zero, residuals, noise scale).

    The Huber scale underestimates noise on short series, so the scale is re-estimated as the standard
    deviation of the residuals the robust fit did not flag (degrees of freedom corrected).
    """
    positions = np.arange(len(detrended)) % period
    fit = sm.RLM(detrended, np.eye(period)[positions], M=sm.robust.norms.HuberT()).fit()
    profile = fit.params - fit.params.mean()
    residual = detrended - profile[positions]
    inliers = np.abs(fit.resid) <= threshold * fit.scale
    degrees_of_freedom = max(int(inliers.sum()) - period, 1)
    scale = float(np.sqrt(np.sum(fit.resid[inliers] ** 2) / degrees_of_freedom))
    return profile, residual, scale


def _anomalies(
    series: pd.Series, expected: np.ndarray, robust_z: np.ndarray, threshold: float
) -> list[Anomaly]:
    return [
        Anomaly(
            date=str(series.index[position].date()),
            value=round(float(series.iloc[position]), 2),
            expected=round(float(expected[position]), 2),
            robust_z=round(float(robust_z[position]), 2),
        )
        for position in np.flatnonzero(np.abs(robust_z) > threshold)
    ]


def detect_patterns(series: pd.Series, period: int, pattern_config: PatternConfig) -> PatternResult:
    values = series.to_numpy()
    threshold = pattern_config.anomaly_z_threshold
    trend = STL(series, period=period, trend=_trend_window(period), robust=True).fit().trend.to_numpy()
    profile, residual, scale = _seasonal_fit(values - trend, period, threshold)
    seasonal = profile[np.arange(len(values)) % period]
    level = float(np.mean(values))
    usable_scale = scale > MIN_RELATIVE_SCALE * max(abs(level), 1.0)
    robust_z = residual / scale if usable_scale else np.zeros_like(residual)
    regular = np.abs(robust_z) <= threshold
    slope = float(np.polyfit(np.arange(len(values)), trend, 1)[0])
    peak, trough = int(profile.argmax()), int(profile.argmin())
    return PatternResult(
        season_period=period,
        trend_direction=_direction(slope, level, pattern_config.stable_trend_threshold),
        trend_slope_per_period=round(slope, 4),
        trend_strength=_strength(trend[regular], residual[regular]),
        seasonal_strength=_strength(seasonal[regular], residual[regular]),
        peak_position=peak,
        trough_position=trough,
        peak_example_date=str(series.index[peak].date()),
        trough_example_date=str(series.index[trough].date()),
        seasonal_profile=[round(float(value), 2) for value in profile],
        anomalies=_anomalies(series, trend + seasonal, robust_z, threshold),
    )
