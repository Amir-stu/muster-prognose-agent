import pytest

from prognose.schemas import QualityProfile
from prognose.tools.sufficiency import evaluate_sufficiency


def _profile(**overrides):
    base = {
        "n_rows": 36,
        "n_expected": 36,
        "valid_observations": 36,
        "start": "2023-01-01",
        "end": "2025-12-01",
        "frequency": "MS",
        "frequency_label": "monatlich",
        "season_period": 12,
        "duplicate_dates": 0,
        "off_grid_dates": 0,
        "missing_periods": 0,
        "nan_values": 0,
        "missing_share": 0.0,
        "full_seasonal_cycles": 3.0,
        "negative_values": 0,
        "zero_share": 0.0,
        "mean": 100.0,
        "std": 10.0,
        "min": 80.0,
        "max": 120.0,
    }
    return QualityProfile(**{**base, **overrides})


def _failed(result):
    return {rule.rule for rule in result.rules if not rule.passed}


def test_gate_when_clean_profile_passes(config):
    result = evaluate_sufficiency(_profile(), config.gate)
    assert result.sufficient is True
    assert _failed(result) == set()
    assert len(result.rules) == 7


def test_gate_when_exactly_at_thresholds_passes(config):
    profile = _profile(valid_observations=24, full_seasonal_cycles=2.0, missing_share=0.10)
    assert evaluate_sufficiency(profile, config.gate).sufficient is True


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"valid_observations": 23}, "beobachtungen"),
        ({"full_seasonal_cycles": 1.99}, "saisonzyklen"),
        ({"missing_share": 0.1001}, "fehlanteil"),
        ({"duplicate_dates": 1}, "doppelte_daten"),
        ({"off_grid_dates": 1}, "datum_ausserhalb_raster"),
        ({"std": 0.0}, "streuung_vorhanden"),
        ({"frequency": None, "frequency_label": None, "season_period": 0}, "frequenz_erkannt"),
    ],
)
def test_gate_when_rule_just_violated_fails_that_rule(config, overrides, rule):
    result = evaluate_sufficiency(_profile(**overrides), config.gate)
    assert result.sufficient is False
    assert rule in _failed(result)


def test_gate_rules_carry_german_description(config):
    result = evaluate_sufficiency(_profile(), config.gate)
    assert all(rule.description for rule in result.rules)
