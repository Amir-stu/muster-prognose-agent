"""Step 01: data quality and history profile, plus the regularised series later steps work on."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from prognose.schemas import QualityProfile

MIN_POINTS_FOR_FREQUENCY = 3
MAJORITY_SHARE = 0.5
WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MONTH_CODES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
DAILY_DAYS = (0.9, 1.1)
WEEKLY_DAYS = (6.5, 7.5)
MONTHLY_DAYS = (27.0, 32.0)
QUARTERLY_DAYS = (88.0, 93.0)


@dataclass(frozen=True)
class FrequencyInfo:
    alias: str
    label: str
    season_period: int


def _within(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def _period_anchor(dates: pd.DatetimeIndex) -> tuple[str, int] | None:
    """('S', month) for period-start dates, ('E', month) for period-end dates, else None."""
    starts = dates[dates.day == 1]
    if len(starts) >= MAJORITY_SHARE * len(dates):
        return "S", int(starts[0].month)
    ends = dates[dates.is_month_end]
    if len(ends) >= MAJORITY_SHARE * len(dates):
        return "E", int(ends[0].month)
    return None


def detect_frequency(dates: pd.DatetimeIndex) -> FrequencyInfo | None:
    if len(dates) < MIN_POINTS_FOR_FREQUENCY:
        return None
    spacing = float(np.median((dates[1:] - dates[:-1]) / pd.Timedelta(days=1)))
    if _within(spacing, DAILY_DAYS):
        return FrequencyInfo("D", "täglich", 7)
    if _within(spacing, WEEKLY_DAYS):
        weekday = int(pd.Series(dates.dayofweek).mode().iloc[0])
        return FrequencyInfo(f"W-{WEEKDAY_CODES[weekday]}", "wöchentlich", 52)
    anchor = _period_anchor(dates)
    if anchor is None:
        return None
    side, month = anchor
    if _within(spacing, MONTHLY_DAYS):
        return FrequencyInfo(f"M{side}", "monatlich", 12)
    if _within(spacing, QUARTERLY_DAYS):
        return FrequencyInfo(f"Q{side}-{MONTH_CODES[month - 1]}", "quartalsweise", 4)
    return None


def _require_columns(frame: pd.DataFrame, *columns: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Spalte fehlt in den Daten: {', '.join(missing)}")


def _value_statistics(values: pd.Series) -> dict[str, float | int]:
    valid = values.dropna()
    if valid.empty:
        return {"negative_values": 0, "zero_share": 0.0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "negative_values": int((valid < 0).sum()),
        "zero_share": round(float((valid == 0).mean()), 4),
        "mean": round(float(valid.mean()), 4),
        "std": round(float(valid.std(ddof=1)), 4) if len(valid) > 1 else 0.0,
        "min": float(valid.min()),
        "max": float(valid.max()),
    }


def profile_series(frame: pd.DataFrame, date_column: str, value_column: str) -> QualityProfile:
    _require_columns(frame, date_column, value_column)
    dates = pd.to_datetime(frame[date_column])
    values = pd.to_numeric(frame[value_column], errors="coerce")
    unique = pd.DatetimeIndex(dates.drop_duplicates().sort_values())
    if unique.empty:
        raise ValueError("Keine Datumswerte in den Daten")
    frequency = detect_frequency(unique)
    expected = unique if frequency is None else pd.date_range(unique[0], unique[-1], freq=frequency.alias)
    missing_periods = len(expected.difference(unique))
    nan_values = int(values.isna().sum())
    period = frequency.season_period if frequency else 0
    return QualityProfile(
        n_rows=len(frame),
        n_expected=len(expected),
        valid_observations=max(len(expected) - missing_periods - nan_values, 0),
        start=str(expected[0].date()),
        end=str(expected[-1].date()),
        frequency=frequency.alias if frequency else None,
        frequency_label=frequency.label if frequency else None,
        season_period=period,
        duplicate_dates=int(dates.duplicated().sum()),
        off_grid_dates=len(unique.difference(expected)),
        missing_periods=missing_periods,
        nan_values=nan_values,
        missing_share=(missing_periods + nan_values) / len(expected),
        full_seasonal_cycles=round(len(expected) / period, 2) if period else 0.0,
        **_value_statistics(values),
    )


def prepare_series(
    frame: pd.DataFrame, profile: QualityProfile, date_column: str, value_column: str
) -> pd.Series:
    """Regular series on the detected grid: duplicates averaged, off-grid dates dropped, gaps interpolated."""
    if profile.frequency is None:
        raise ValueError("Ohne erkannte Frequenz kann keine regelmäßige Reihe gebildet werden")
    values = pd.to_numeric(frame[value_column], errors="coerce").astype(float)
    raw = pd.Series(values.to_numpy(), index=pd.to_datetime(frame[date_column]))
    grid = pd.date_range(profile.start, profile.end, freq=profile.frequency)
    regular = raw.groupby(level=0).mean().reindex(grid)
    filled = regular.interpolate(method="time").ffill().bfill()
    return pd.Series(filled.to_numpy(dtype=float), index=grid, name=value_column)
