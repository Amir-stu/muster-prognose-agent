"""Step 02: rule-based "Ausreichende Daten vorhanden?" gate. No LLM is involved in this decision."""

from prognose.config import GateConfig
from prognose.schemas import GateResult, QualityProfile, RuleResult

FLOAT_TOLERANCE = 1e-12


def _rule(rule: str, description: str, value: float, threshold: float, comparison: str) -> RuleResult:
    checks = {
        ">=": value >= threshold - FLOAT_TOLERANCE,
        "<=": value <= threshold + FLOAT_TOLERANCE,
        ">": value > threshold,
    }
    return RuleResult(
        rule=rule,
        description=description,
        value=float(value),
        threshold=float(threshold),
        comparison=comparison,
        passed=checks[comparison],
    )


def evaluate_sufficiency(profile: QualityProfile, gate: GateConfig) -> GateResult:
    rules = [
        _rule(
            "frequenz_erkannt",
            "Eine regelmäßige Frequenz (täglich, wöchentlich, monatlich, quartalsweise) ist erkennbar",
            1.0 if profile.frequency else 0.0,
            1.0,
            ">=",
        ),
        _rule(
            "beobachtungen",
            "Mindestanzahl gültiger Beobachtungen",
            profile.valid_observations,
            gate.min_observations,
            ">=",
        ),
        _rule(
            "saisonzyklen",
            "Mindestanzahl voller Saisonzyklen",
            profile.full_seasonal_cycles,
            gate.min_seasonal_cycles,
            ">=",
        ),
        _rule(
            "fehlanteil",
            "Höchstanteil fehlender Perioden oder Werte",
            profile.missing_share,
            gate.max_missing_share,
            "<=",
        ),
        _rule(
            "doppelte_daten",
            "Höchstzahl doppelter Datumswerte",
            profile.duplicate_dates,
            gate.max_duplicate_dates,
            "<=",
        ),
        _rule(
            "datum_ausserhalb_raster",
            "Höchstzahl von Datumswerten außerhalb des Rasters",
            profile.off_grid_dates,
            gate.max_off_grid_dates,
            "<=",
        ),
        _rule(
            "streuung_vorhanden", "Die Reihe schwankt (Standardabweichung größer null)", profile.std, 0.0, ">"
        ),
    ]
    return GateResult(sufficient=all(rule.passed for rule in rules), rules=rules)
