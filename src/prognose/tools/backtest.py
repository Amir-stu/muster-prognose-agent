"""Step 05: rolling-origin backtest of every configured model on held-out history."""

import math

import numpy as np
import pandas as pd

from prognose.config import BacktestConfig
from prognose.metrics import coverage, mase, smape
from prognose.schemas import BacktestResult, FoldScore, ModelScore
from prognose.tools.models import fit_forecast

METRIC_DECIMALS = 4
ERROR_MESSAGE_LIMIT = 200
TOO_SHORT_MESSAGE = "zu wenig Historie für einen Backtest mit diesem Horizont"


def fold_origins(n_observations: int, horizon: int, folds: int, min_train: int) -> list[int]:
    """Training-window end positions; the last fold ends exactly at the end of the series."""
    origins = [n_observations - horizon * (folds - index) for index in range(folds)]
    return [origin for origin in origins if origin >= min_train]


def _score_fold(
    model: str, series: pd.Series, origin: int, fold: int, horizon: int, period: int
) -> FoldScore:
    train = series.iloc[:origin]
    actual = series.iloc[origin : origin + horizon].to_numpy()
    forecast = fit_forecast(model, train, horizon, period)
    return FoldScore(
        fold=fold,
        train_end=str(train.index[-1].date()),
        mase=round(mase(actual, forecast["point"].to_numpy(), train.to_numpy(), period), METRIC_DECIMALS),
        smape=round(smape(actual, forecast["point"].to_numpy()), METRIC_DECIMALS),
        coverage_80=round(
            coverage(actual, forecast["lower_80"].to_numpy(), forecast["upper_80"].to_numpy()), 4
        ),
        coverage_95=round(
            coverage(actual, forecast["lower_95"].to_numpy(), forecast["upper_95"].to_numpy()), 4
        ),
    )


def _failed(model: str, message: str) -> ModelScore:
    return ModelScore(
        model=model,
        status="failed",
        error=message[:ERROR_MESSAGE_LIMIT],
        folds=[],
        mean_mase=None,
        mean_smape=None,
        mean_coverage_80=None,
        mean_coverage_95=None,
    )


def _mean(values: list[float]) -> float:
    return round(float(np.mean(values)), METRIC_DECIMALS)


def _score_model(model: str, series: pd.Series, origins: list[int], horizon: int, period: int) -> ModelScore:
    if not origins:
        return _failed(model, TOO_SHORT_MESSAGE)
    try:
        folds = [
            _score_fold(model, series, origin, index, horizon, period) for index, origin in enumerate(origins)
        ]
    except Exception as error:  # statsmodels raises many error types; the failure is recorded, not hidden
        return _failed(model, f"{type(error).__name__}: {error}")
    return ModelScore(
        model=model,
        status="ok",
        error=None,
        folds=folds,
        mean_mase=_mean([fold.mase for fold in folds]),
        mean_smape=_mean([fold.smape for fold in folds]),
        mean_coverage_80=_mean([fold.coverage_80 for fold in folds]),
        mean_coverage_95=_mean([fold.coverage_95 for fold in folds]),
    )


def run_backtest(
    series: pd.Series, period: int, horizon: int, backtest_config: BacktestConfig
) -> BacktestResult:
    min_train = math.ceil(backtest_config.min_train_cycles * period)
    origins = fold_origins(len(series), horizon, backtest_config.folds, min_train)
    models = [_score_model(model, series, origins, horizon, period) for model in backtest_config.models]
    return BacktestResult(horizon=horizon, folds_run=len(origins), models=models)
