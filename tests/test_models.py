import numpy as np
import pytest

from prognose.synthetic import SyntheticSpec, make_series
from prognose.tools.models import MODEL_NAMES, fit_forecast
from prognose.tools.profile import prepare_series, profile_series


def _series(spec):
    frame = make_series(spec)
    return prepare_series(frame, profile_series(frame, "datum", "wert"), "datum", "wert")


@pytest.fixture
def series():
    return _series(SyntheticSpec(periods=60))


@pytest.mark.parametrize("model", MODEL_NAMES)
def test_fit_forecast_when_each_model_returns_ordered_bands(series, model):
    result = fit_forecast(model, series, horizon=6, period=12)
    assert len(result) == 6
    assert str(result.index[0].date()) == "2025-01-01"
    assert (result["lower_95"] <= result["lower_80"] + 1e-9).all()
    assert (result["lower_80"] <= result["point"] + 1e-9).all()
    assert (result["point"] <= result["upper_80"] + 1e-9).all()
    assert (result["upper_80"] <= result["upper_95"] + 1e-9).all()


def test_seasonal_naive_when_known_series_repeats_last_cycle():
    series = _series(SyntheticSpec(periods=36, noise_sd=0.0, slope=0.0))
    result = fit_forecast("saisonal_naiv", series, horizon=12, period=12)
    assert np.allclose(result["point"].to_numpy(), series.iloc[-12:].to_numpy())


def test_seasonal_naive_interval_widens_after_one_cycle(series):
    result = fit_forecast("saisonal_naiv", series, horizon=24, period=12)
    width = (result["upper_95"] - result["lower_95"]).to_numpy()
    assert width[12] == pytest.approx(width[0] * np.sqrt(2))


def test_fit_forecast_when_unknown_model_raises(series):
    with pytest.raises(ValueError, match="unbekannt"):
        fit_forecast("orakel", series, horizon=3, period=12)
