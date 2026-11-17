import math

import numpy as np
import pytest

from prognose.metrics import coverage, mase, smape


def test_mase_when_non_seasonal_scale_one_returns_mean_abs_error():
    train = np.array([1, 2, 3, 4, 5, 6], dtype=float)
    assert mase(np.array([7.0, 8.0]), np.array([6.0, 10.0]), train, period=1) == pytest.approx(1.5)


def test_mase_when_seasonal_period_two_uses_lag_two_scale():
    train = np.array([1, 3, 2, 4, 3, 5], dtype=float)
    assert mase(np.array([6.0]), np.array([4.0]), train, period=2) == pytest.approx(2.0)


def test_mase_when_perfect_forecast_returns_zero():
    train = np.array([1, 2, 3, 4], dtype=float)
    assert mase(np.array([5.0, 6.0]), np.array([5.0, 6.0]), train, period=1) == 0.0


def test_mase_when_training_scale_zero_raises():
    with pytest.raises(ValueError, match="Skalierung"):
        mase(np.array([1.0]), np.array([2.0]), np.array([3.0, 3.0, 3.0]), period=1)


def test_mase_when_training_shorter_than_period_raises():
    with pytest.raises(ValueError):
        mase(np.array([1.0]), np.array([1.0]), np.array([1.0, 2.0]), period=12)


def test_smape_when_ten_percent_over_returns_known_value():
    assert smape(np.array([100.0]), np.array([110.0])) == pytest.approx(2 * 10 / 210 * 100)


def test_smape_when_both_zero_counts_as_zero_error():
    assert smape(np.array([0.0, 100.0]), np.array([0.0, 100.0])) == 0.0


def test_smape_when_symmetric_pair_is_equal():
    assert smape(np.array([100.0]), np.array([50.0])) == pytest.approx(
        smape(np.array([50.0]), np.array([100.0]))
    )


def test_coverage_when_half_inside_returns_half():
    actual = np.array([1.0, 2.0, 3.0, 4.0])
    lower = np.array([0.0, 0.0, 4.0, 0.0])
    upper = np.array([2.0, 1.0, 5.0, 5.0])
    assert coverage(actual, lower, upper) == 0.5


def test_coverage_when_on_bounds_counts_inside():
    assert coverage(np.array([2.0]), np.array([2.0]), np.array([2.0])) == 1.0


def test_metrics_when_lengths_differ_raise():
    with pytest.raises(ValueError):
        smape(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        coverage(np.array([1.0]), np.array([0.0, 0.0]), np.array([2.0]))
    with pytest.raises(ValueError):
        mase(np.array([1.0]), np.array([1.0, 2.0]), np.array([1.0, 2.0, 4.0]), period=1)


def test_mase_result_is_finite_float():
    value = mase(np.array([3.0]), np.array([2.0]), np.array([1.0, 2.0]), period=1)
    assert isinstance(value, float) and math.isfinite(value)
