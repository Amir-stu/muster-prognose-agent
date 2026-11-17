import numpy as np
import pandas as pd
import pytest

from prognose.synthetic import SyntheticSpec, make_series
from prognose.tools.profile import prepare_series, profile_series


def _profile(frame):
    return profile_series(frame, "datum", "wert")


def test_profile_when_clean_monthly_detects_frequency_and_cycles(monthly_frame):
    result = _profile(monthly_frame)
    assert result.frequency == "MS"
    assert result.frequency_label == "monatlich"
    assert result.season_period == 12
    assert result.missing_periods == 0
    assert result.full_seasonal_cycles == 6.0
    assert result.valid_observations == 72
    assert result.start == "2020-01-01"
    assert result.end == "2025-12-01"


def test_profile_when_rows_dropped_counts_missing(monthly_frame):
    result = _profile(monthly_frame.drop(index=[10, 11, 12]))
    assert result.missing_periods == 3
    assert result.missing_share == pytest.approx(3 / 72)
    assert result.valid_observations == 69


def test_profile_when_duplicate_date_counts_it(monthly_frame):
    frame = pd.concat([monthly_frame, monthly_frame.iloc[[4]]], ignore_index=True)
    assert _profile(frame).duplicate_dates == 1


def test_profile_when_nan_value_counts_it(monthly_frame):
    frame = monthly_frame.assign(wert=monthly_frame["wert"].where(monthly_frame.index != 3))
    result = _profile(frame)
    assert result.nan_values == 1
    assert result.valid_observations == 71


@pytest.mark.parametrize(
    ("freq", "label", "period"),
    [
        ("W-MON", "wöchentlich", 52),
        ("D", "täglich", 7),
        ("QS-JAN", "quartalsweise", 4),
        ("ME", "monatlich", 12),
    ],
)
def test_profile_when_other_frequencies_detects_them(freq, label, period):
    result = _profile(make_series(SyntheticSpec(freq=freq, periods=40)))
    assert result.frequency_label == label
    assert result.season_period == period
    assert result.missing_periods == 0


def test_profile_when_too_few_rows_frequency_unknown():
    result = _profile(make_series(SyntheticSpec(periods=2)))
    assert result.frequency is None
    assert result.season_period == 0


def test_profile_when_irregular_spacing_frequency_unknown():
    dates = pd.to_datetime(["2024-01-01", "2024-01-04", "2024-01-07", "2024-01-10"])
    frame = pd.DataFrame({"datum": dates, "wert": [1.0, 2.0, 3.0, 4.0]})
    assert _profile(frame).frequency is None


def test_profile_when_off_grid_date_counts_it(monthly_frame):
    extra = pd.DataFrame({"datum": [pd.Timestamp("2020-03-15")], "wert": [100.0]})
    result = _profile(pd.concat([monthly_frame, extra], ignore_index=True))
    assert result.off_grid_dates == 1
    assert result.frequency == "MS"


def test_profile_when_column_missing_raises(monthly_frame):
    with pytest.raises(ValueError, match="umsatz"):
        profile_series(monthly_frame, "datum", "umsatz")


def test_profile_reports_value_statistics():
    frame = pd.DataFrame(
        {"datum": pd.date_range("2024-01-01", periods=4, freq="D"), "wert": [-1.0, 0.0, 0.0, 5.0]}
    )
    result = _profile(frame)
    assert result.negative_values == 1
    assert result.zero_share == 0.5
    assert result.min == -1.0
    assert result.max == 5.0
    assert result.mean == 1.0


def test_prepare_series_when_gaps_interpolates_to_full_grid(monthly_frame):
    frame = monthly_frame.drop(index=[10])
    series = prepare_series(frame, _profile(frame), "datum", "wert")
    assert len(series) == 72
    assert series.index.freqstr == "MS"
    expected = (monthly_frame["wert"][9] + monthly_frame["wert"][11]) / 2
    assert series.iloc[10] == pytest.approx(expected, rel=0.02)
    assert not series.isna().any()


def test_prepare_series_when_duplicates_averages_them(monthly_frame):
    duplicate = pd.DataFrame({"datum": [monthly_frame["datum"][0]], "wert": [monthly_frame["wert"][0] + 10]})
    frame = pd.concat([monthly_frame, duplicate], ignore_index=True)
    series = prepare_series(frame, _profile(frame), "datum", "wert")
    assert series.iloc[0] == pytest.approx(monthly_frame["wert"][0] + 5)


def test_prepare_series_when_frequency_unknown_raises():
    frame = make_series(SyntheticSpec(periods=2))
    with pytest.raises(ValueError):
        prepare_series(frame, _profile(frame), "datum", "wert")


def test_prepare_series_values_are_float(monthly_frame):
    series = prepare_series(monthly_frame, _profile(monthly_frame), "datum", "wert")
    assert series.dtype == np.float64
