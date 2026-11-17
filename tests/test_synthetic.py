import numpy as np

from prognose.synthetic import SyntheticSpec, make_series


def test_make_series_when_same_seed_is_deterministic():
    assert make_series(SyntheticSpec()).equals(make_series(SyntheticSpec()))


def test_make_series_when_anomaly_planted_value_jumps():
    base = make_series(SyntheticSpec(periods=24))
    spiked = make_series(SyntheticSpec(periods=24, anomaly_positions=(5,), anomaly_size=40.0))
    difference = spiked["wert"].to_numpy() - base["wert"].to_numpy()
    assert np.isclose(difference[5], 40.0)
    assert np.allclose(np.delete(difference, 5), 0.0)


def test_make_series_when_custom_columns_uses_them():
    frame = make_series(SyntheticSpec(periods=12), date_column="d", value_column="v")
    assert list(frame.columns) == ["d", "v"]
    assert len(frame) == 12
