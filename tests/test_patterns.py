import pytest

from prognose.synthetic import SyntheticSpec, make_series
from prognose.tools.patterns import detect_patterns
from prognose.tools.profile import prepare_series, profile_series


def _series(spec):
    frame = make_series(spec)
    return prepare_series(frame, profile_series(frame, "datum", "wert"), "datum", "wert")


def test_patterns_when_rising_trend_detects_slope_and_season(config):
    series = _series(SyntheticSpec(periods=72, slope=0.8, anomaly_positions=(30, 55)))
    result = detect_patterns(series, 12, config.patterns)
    assert result.trend_direction == "steigend"
    assert result.trend_slope_per_period == pytest.approx(0.8, abs=0.15)
    assert result.seasonal_strength > 0.8
    assert result.peak_position == 3
    assert result.trough_position == 9
    assert result.peak_example_date == "2020-04-01"


def test_patterns_when_anomalies_planted_finds_them(config):
    series = _series(SyntheticSpec(periods=72, anomaly_positions=(30, 55)))
    result = detect_patterns(series, 12, config.patterns)
    found = {anomaly.date for anomaly in result.anomalies}
    assert {"2022-07-01", "2024-08-01"} <= found
    assert len(result.anomalies) <= 4
    spike = next(a for a in result.anomalies if a.date == "2022-07-01")
    assert spike.value - spike.expected == pytest.approx(40, abs=8)


def test_patterns_when_falling_trend_says_fallend(config):
    series = _series(SyntheticSpec(periods=72, slope=-0.8, level=200.0))
    assert detect_patterns(series, 12, config.patterns).trend_direction == "fallend"


def test_patterns_when_flat_says_stabil(config):
    series = _series(SyntheticSpec(periods=72, slope=0.0))
    result = detect_patterns(series, 12, config.patterns)
    assert result.trend_direction == "stabil"
    assert len(result.seasonal_profile) == 12


def test_patterns_when_no_noise_has_no_anomalies(config):
    series = _series(SyntheticSpec(periods=48, noise_sd=0.0))
    assert detect_patterns(series, 12, config.patterns).anomalies == []
