"""Step 06: choose the model on backtest evidence and forecast with prediction intervals."""

import pandas as pd

from prognose.schemas import BacktestResult, ForecastPoint, ForecastResult, ModelChoice, ModelScore
from prognose.tools.models import BASELINE_MODEL, fit_forecast

VALUE_DECIMALS = 2


def _improvement(best: ModelScore, baseline: ModelScore | None) -> float | None:
    if baseline is None or not baseline.mean_mase:
        return None
    return round((1 - best.mean_mase / baseline.mean_mase) * 100, 2)


def choose_model(backtest: BacktestResult) -> ModelChoice:
    """Lowest mean MASE wins; ties go to the baseline, so a model must strictly beat seasonal-naive."""
    usable = [score for score in backtest.models if score.status == "ok" and score.mean_mase is not None]
    baseline = next((score for score in usable if score.model == BASELINE_MODEL), None)
    if not usable:
        return ModelChoice(
            model=BASELINE_MODEL,
            baseline_model=BASELINE_MODEL,
            mase=None,
            baseline_mase=None,
            beats_baseline=False,
            improvement_vs_baseline_pct=None,
            backtest_coverage_80=None,
            backtest_coverage_95=None,
        )
    best = min(usable, key=lambda score: (score.mean_mase, score.model != BASELINE_MODEL))
    return ModelChoice(
        model=best.model,
        baseline_model=BASELINE_MODEL,
        mase=best.mean_mase,
        baseline_mase=baseline.mean_mase if baseline else None,
        beats_baseline=baseline is not None and best.model != BASELINE_MODEL,
        improvement_vs_baseline_pct=_improvement(best, baseline),
        backtest_coverage_80=best.mean_coverage_80,
        backtest_coverage_95=best.mean_coverage_95,
    )


def _points(frame: pd.DataFrame) -> list[ForecastPoint]:
    rounded = frame.round(VALUE_DECIMALS)
    return [
        ForecastPoint(date=str(date.date()), **{column: float(row[column]) for column in rounded.columns})
        for date, row in rounded.iterrows()
    ]


def make_forecast(series: pd.Series, backtest: BacktestResult, horizon: int, period: int) -> ForecastResult:
    choice = choose_model(backtest)
    frame = fit_forecast(choice.model, series, horizon, period)
    return ForecastResult(**choice.model_dump(), horizon=horizon, points=_points(frame))
