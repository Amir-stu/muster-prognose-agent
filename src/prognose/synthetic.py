"""Synthetic series with known trend, seasonality and planted anomalies, for tests and demo runs."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SyntheticSpec:
    start: str = "2020-01-01"
    freq: str = "MS"
    periods: int = 72
    level: float = 100.0
    slope: float = 0.8
    season_period: int = 12
    season_amplitude: float = 15.0
    noise_sd: float = 2.0
    anomaly_positions: tuple[int, ...] = ()
    anomaly_size: float = 40.0
    seed: int = 7


def make_series(spec: SyntheticSpec, date_column: str = "datum", value_column: str = "wert") -> pd.DataFrame:
    rng = np.random.default_rng(spec.seed)
    steps = np.arange(spec.periods)
    season = spec.season_amplitude * np.sin(2 * np.pi * steps / spec.season_period)
    noise = rng.normal(0.0, spec.noise_sd, spec.periods)
    spikes = np.isin(steps, spec.anomaly_positions) * spec.anomaly_size
    values = spec.level + spec.slope * steps + season + noise + spikes
    dates = pd.date_range(spec.start, periods=spec.periods, freq=spec.freq)
    return pd.DataFrame({date_column: dates, value_column: values.round(2)})
