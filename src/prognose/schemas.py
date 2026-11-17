"""Pydantic contracts for every step output; the orchestrator only passes data that validates."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class QualityProfile(Frozen):
    n_rows: int
    n_expected: int
    valid_observations: int
    start: str
    end: str
    frequency: str | None
    frequency_label: str | None
    season_period: int
    duplicate_dates: int
    off_grid_dates: int
    missing_periods: int
    nan_values: int
    missing_share: float
    full_seasonal_cycles: float
    negative_values: int
    zero_share: float
    mean: float
    std: float
    min: float
    max: float


class RuleResult(Frozen):
    rule: str
    description: str
    value: float
    threshold: float
    comparison: Literal[">=", "<=", ">"]
    passed: bool


class GateResult(Frozen):
    sufficient: bool
    rules: list[RuleResult]


class Anomaly(Frozen):
    date: str
    value: float
    expected: float
    robust_z: float


class PatternResult(Frozen):
    season_period: int
    trend_direction: Literal["steigend", "fallend", "stabil"]
    trend_slope_per_period: float
    trend_strength: float
    seasonal_strength: float
    peak_position: int
    trough_position: int
    peak_example_date: str
    trough_example_date: str
    seasonal_profile: list[float]
    anomalies: list[Anomaly]


class FoldScore(Frozen):
    fold: int
    train_end: str
    mase: float
    smape: float
    coverage_80: float
    coverage_95: float


class ModelScore(Frozen):
    model: str
    status: Literal["ok", "failed"]
    error: str | None
    folds: list[FoldScore]
    mean_mase: float | None
    mean_smape: float | None
    mean_coverage_80: float | None
    mean_coverage_95: float | None


class BacktestResult(Frozen):
    horizon: int
    folds_run: int
    models: list[ModelScore]


class ModelChoice(Frozen):
    model: str
    baseline_model: str
    mase: float | None
    baseline_mase: float | None
    beats_baseline: bool
    improvement_vs_baseline_pct: float | None
    backtest_coverage_80: float | None
    backtest_coverage_95: float | None


class ForecastPoint(Frozen):
    date: str
    point: float
    lower_80: float
    upper_80: float
    lower_95: float
    upper_95: float


class ForecastResult(ModelChoice):
    horizon: int
    points: list[ForecastPoint]


class VizResult(Frozen):
    chart_file: str
    history_points: int
    forecast_points: int
    anomaly_points: int


class ExportResult(Frozen):
    excel_file: str
    pptx_file: str
    slides: int


class Interpretation(Frozen):
    summary: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list, max_length=5)

    def full_text(self) -> str:
        return "\n".join([self.summary, *self.notes])


class ReviewDecision(Frozen):
    decision: Literal["freigegeben", "anpassen"]
    comment: str
    decided_at: str


class Handover(Frozen):
    reason: Literal["daten_nachgefordert", "anpassung"]
    data_file: str
    horizon: int
    comment: str
    handed_over_at: str


class IterationTarget(Frozen):
    iteration: int
    horizon: int
    data_file: str


class StepRecord(Frozen):
    step: str
    iteration: int
    finished_at: str
    cost_usd: float


RunStatus = Literal[
    "running", "waiting_for_data", "awaiting_review", "completed", "stopped_max_loops", "failed"
]


class RunState(Frozen):
    run_id: str
    status: RunStatus
    iteration: int
    data_file: str
    horizon: int
    llm_enabled: bool
    completed_steps: list[str]
    history: list[StepRecord]
    cost_usd: float
    error: str | None
