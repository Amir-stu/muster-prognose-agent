import pytest

from prognose.schemas import BacktestResult, ModelScore
from prognose.synthetic import SyntheticSpec, make_series
from prognose.tools.backtest import run_backtest
from prognose.tools.forecast import choose_model, make_forecast
from prognose.tools.profile import prepare_series, profile_series


def _score(model, mase, status="ok"):
    ok = status == "ok"
    return ModelScore(
        model=model,
        status=status,
        error=None if ok else "x",
        folds=[],
        mean_mase=mase if ok else None,
        mean_smape=1.0 if ok else None,
        mean_coverage_80=0.8 if ok else None,
        mean_coverage_95=0.95 if ok else None,
    )


def _backtest(*scores):
    return BacktestResult(horizon=12, folds_run=3, models=list(scores))


def test_choose_model_when_ets_lowest_picks_ets():
    choice = choose_model(_backtest(_score("saisonal_naiv", 1.2), _score("ets", 0.6), _score("theta", 0.9)))
    assert choice.model == "ets"
    assert choice.beats_baseline is True
    assert choice.improvement_vs_baseline_pct == pytest.approx(50.0)


def test_choose_model_when_tie_prefers_baseline():
    choice = choose_model(_backtest(_score("ets", 1.0), _score("saisonal_naiv", 1.0)))
    assert choice.model == "saisonal_naiv"
    assert choice.beats_baseline is False


def test_choose_model_when_baseline_best_keeps_baseline():
    choice = choose_model(_backtest(_score("saisonal_naiv", 0.7), _score("ets", 0.9)))
    assert choice.model == "saisonal_naiv"
    assert choice.beats_baseline is False
    assert choice.improvement_vs_baseline_pct == 0.0


def test_choose_model_ignores_failed_models():
    choice = choose_model(_backtest(_score("saisonal_naiv", 1.0), _score("ets", 0.1, status="failed")))
    assert choice.model == "saisonal_naiv"


def test_choose_model_when_all_failed_falls_back_to_baseline():
    choice = choose_model(_backtest(_score("saisonal_naiv", 1, "failed"), _score("ets", 1, "failed")))
    assert choice.model == "saisonal_naiv"
    assert choice.mase is None
    assert choice.beats_baseline is False
    assert choice.improvement_vs_baseline_pct is None


def test_choose_model_when_baseline_failed_has_no_comparison():
    choice = choose_model(_backtest(_score("saisonal_naiv", 1, "failed"), _score("ets", 0.5)))
    assert choice.model == "ets"
    assert choice.beats_baseline is False
    assert choice.baseline_mase is None


def test_make_forecast_returns_horizon_points_with_ordered_bands(config):
    frame = make_series(SyntheticSpec(periods=72))
    series = prepare_series(frame, profile_series(frame, "datum", "wert"), "datum", "wert")
    backtest = run_backtest(series, period=12, horizon=12, backtest_config=config.backtest)
    result = make_forecast(series, backtest, horizon=12, period=12)
    assert len(result.points) == 12
    assert result.points[0].date == "2026-01-01"
    assert result.model != "saisonal_naiv"
    assert result.beats_baseline is True
    for point in result.points:
        assert point.lower_95 <= point.lower_80 <= point.point <= point.upper_80 <= point.upper_95
