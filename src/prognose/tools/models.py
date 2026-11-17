"""Forecasting models with 80 % and 95 % prediction intervals, all returning the same frame shape."""

import warnings
from collections.abc import Callable
from statistics import NormalDist

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel
from statsmodels.tsa.forecasting.theta import ThetaModel
from statsmodels.tsa.statespace.sarimax import SARIMAX

BASELINE_MODEL = "saisonal_naiv"
MODEL_NAMES = (BASELINE_MODEL, "ets", "sarima", "theta")
ALPHA_80 = 0.20
ALPHA_95 = 0.05
SARIMA_ORDER = (1, 1, 1)
SARIMA_SEASONAL_ORDER = (0, 1, 1)
COLUMNS = ("point", "lower_80", "upper_80", "lower_95", "upper_95")


def _future_index(series: pd.Series, horizon: int) -> pd.DatetimeIndex:
    return pd.date_range(series.index[-1], periods=horizon + 1, freq=series.index.freq)[1:]


def _frame(index: pd.DatetimeIndex, point, lower_80, upper_80, lower_95, upper_95) -> pd.DataFrame:
    data = {
        name: np.asarray(values, dtype=float)
        for name, values in zip(COLUMNS, (point, lower_80, upper_80, lower_95, upper_95), strict=True)
    }
    frame = pd.DataFrame(data, index=index)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Modell lieferte nicht-endliche Prognosewerte")
    return frame


def _seasonal_naive(series: pd.Series, horizon: int, period: int) -> pd.DataFrame:
    values = series.to_numpy()
    point = np.array([values[-period + (step % period)] for step in range(horizon)])
    residuals = values[period:] - values[:-period]
    sigma = float(np.sqrt(np.mean(residuals**2)))
    standard_error = sigma * np.sqrt(np.arange(horizon) // period + 1)
    z_80, z_95 = NormalDist().inv_cdf(1 - ALPHA_80 / 2), NormalDist().inv_cdf(1 - ALPHA_95 / 2)
    return _frame(
        _future_index(series, horizon),
        point,
        point - z_80 * standard_error,
        point + z_80 * standard_error,
        point - z_95 * standard_error,
        point + z_95 * standard_error,
    )


def _ets(series: pd.Series, horizon: int, period: int) -> pd.DataFrame:
    fitted = ETSModel(
        series, error="add", trend="add", damped_trend=True, seasonal="add", seasonal_periods=period
    ).fit(disp=False)
    prediction = fitted.get_prediction(start=len(series), end=len(series) + horizon - 1)
    band_80 = prediction.summary_frame(alpha=ALPHA_80)
    band_95 = prediction.summary_frame(alpha=ALPHA_95)
    return _frame(
        _future_index(series, horizon),
        band_80["mean"],
        band_80["pi_lower"],
        band_80["pi_upper"],
        band_95["pi_lower"],
        band_95["pi_upper"],
    )


def _sarima(series: pd.Series, horizon: int, period: int) -> pd.DataFrame:
    fitted = SARIMAX(series, order=SARIMA_ORDER, seasonal_order=(*SARIMA_SEASONAL_ORDER, period)).fit(
        disp=False
    )
    forecast = fitted.get_forecast(horizon)
    band_80 = forecast.conf_int(alpha=ALPHA_80).to_numpy()
    band_95 = forecast.conf_int(alpha=ALPHA_95).to_numpy()
    return _frame(
        _future_index(series, horizon),
        forecast.predicted_mean,
        band_80[:, 0],
        band_80[:, 1],
        band_95[:, 0],
        band_95[:, 1],
    )


def _theta(series: pd.Series, horizon: int, period: int) -> pd.DataFrame:
    fitted = ThetaModel(series, period=period).fit()
    band_80 = fitted.prediction_intervals(horizon, alpha=ALPHA_80)
    band_95 = fitted.prediction_intervals(horizon, alpha=ALPHA_95)
    return _frame(
        _future_index(series, horizon),
        fitted.forecast(horizon),
        band_80["lower"],
        band_80["upper"],
        band_95["lower"],
        band_95["upper"],
    )


MODELS: dict[str, Callable[[pd.Series, int, int], pd.DataFrame]] = {
    BASELINE_MODEL: _seasonal_naive,
    "ets": _ets,
    "sarima": _sarima,
    "theta": _theta,
}


def fit_forecast(model: str, series: pd.Series, horizon: int, period: int) -> pd.DataFrame:
    if model not in MODELS:
        raise ValueError(f"Modell unbekannt: {model}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return MODELS[model](series, horizon, period)
