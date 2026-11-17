from prognose.config import BacktestConfig
from prognose.synthetic import SyntheticSpec, make_series
from prognose.tools.backtest import fold_origins, run_backtest
from prognose.tools.profile import prepare_series, profile_series


def _series(periods):
    frame = make_series(SyntheticSpec(periods=periods))
    return prepare_series(frame, profile_series(frame, "datum", "wert"), "datum", "wert")


def test_fold_origins_when_enough_history_returns_all():
    assert fold_origins(72, horizon=12, folds=3, min_train=24) == [36, 48, 60]


def test_fold_origins_when_short_history_drops_early_folds():
    assert fold_origins(48, horizon=12, folds=3, min_train=24) == [24, 36]
    assert fold_origins(30, horizon=12, folds=3, min_train=24) == []


def test_backtest_when_trend_present_models_beat_naive(config):
    result = run_backtest(_series(72), period=12, horizon=12, backtest_config=config.backtest)
    assert result.folds_run == 3
    scores = {score.model: score for score in result.models}
    assert all(score.status == "ok" for score in scores.values())
    best = min(scores.values(), key=lambda score: score.mean_mase)
    assert best.model != "saisonal_naiv"
    assert all(0.0 <= score.mean_coverage_95 <= 1.0 for score in scores.values())
    assert len(scores["ets"].folds) == 3


def test_backtest_when_too_short_marks_models_failed(config):
    result = run_backtest(_series(30), period=12, horizon=12, backtest_config=config.backtest)
    assert result.folds_run == 0
    assert all(score.status == "failed" for score in result.models)
    assert all("Historie" in score.error for score in result.models)


def test_backtest_when_model_errors_records_failure():
    backtest_config = BacktestConfig(folds=2, models=("saisonal_naiv", "orakel"), min_train_cycles=2.0)
    result = run_backtest(_series(60), period=12, horizon=6, backtest_config=backtest_config)
    scores = {score.model: score for score in result.models}
    assert scores["saisonal_naiv"].status == "ok"
    assert scores["orakel"].status == "failed"
    assert "unbekannt" in scores["orakel"].error
