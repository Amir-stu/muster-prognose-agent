"""Typed view of config.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GateConfig:
    min_observations: int
    min_seasonal_cycles: float
    max_missing_share: float
    max_duplicate_dates: int
    max_off_grid_dates: int


@dataclass(frozen=True)
class PatternConfig:
    anomaly_z_threshold: float
    stable_trend_threshold: float


@dataclass(frozen=True)
class BacktestConfig:
    folds: int
    models: tuple[str, ...]
    min_train_cycles: float


@dataclass(frozen=True)
class RunConfig:
    max_iterations: int
    default_horizon: int
    date_column: str
    value_column: str


@dataclass(frozen=True)
class LlmConfig:
    model: str
    max_budget_usd: float
    timeout_s: int
    retries: int


@dataclass(frozen=True)
class Config:
    gate: GateConfig
    patterns: PatternConfig
    backtest: BacktestConfig
    run: RunConfig
    llm: LlmConfig


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    backtest = data["backtest"]
    return Config(
        gate=GateConfig(**data["gate"]),
        patterns=PatternConfig(**data["patterns"]),
        backtest=BacktestConfig(**{**backtest, "models": tuple(backtest["models"])}),
        run=RunConfig(**data["run"]),
        llm=LlmConfig(**data["llm"]),
    )
