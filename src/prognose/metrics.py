"""Forecast accuracy metrics: MASE, sMAPE, interval coverage."""

import numpy as np


def _require_same_length(*arrays: np.ndarray) -> None:
    if len({len(array) for array in arrays}) != 1:
        raise ValueError("Arrays haben unterschiedliche Längen")


def mase(actual: np.ndarray, forecast: np.ndarray, train: np.ndarray, period: int) -> float:
    """Mean absolute error scaled by the in-sample seasonal-naive error of the training window."""
    _require_same_length(actual, forecast)
    if len(train) <= period:
        raise ValueError("Trainingsfenster ist kürzer als eine Saisonperiode")
    scale = float(np.mean(np.abs(train[period:] - train[:-period])))
    if scale == 0.0:
        raise ValueError("Skalierung ist null: Trainingsreihe hat keine saisonale Veränderung")
    return float(np.mean(np.abs(actual - forecast)) / scale)


def smape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Symmetric MAPE in percent; a period where actual and forecast are both zero counts as zero error."""
    _require_same_length(actual, forecast)
    denominator = np.abs(actual) + np.abs(forecast)
    safe = np.where(denominator == 0, 1.0, denominator)
    terms = np.where(denominator == 0, 0.0, 2 * np.abs(forecast - actual) / safe)
    return float(np.mean(terms) * 100)


def coverage(actual: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Share of actuals inside [lower, upper], bounds inclusive."""
    _require_same_length(actual, lower, upper)
    return float(np.mean((actual >= lower) & (actual <= upper)))
