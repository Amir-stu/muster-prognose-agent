"""Assemble the six briefing slides from step outputs and their interpretations."""

from dataclasses import dataclass
from pathlib import Path

from prognose.schemas import (
    BacktestResult,
    ForecastResult,
    Interpretation,
    PatternResult,
    QualityProfile,
    ReviewDecision,
)
from prognose.tools.export_pptx import SlideContent
from prognose.tools.formatting import german_number, german_percent


@dataclass(frozen=True)
class BriefingInputs:
    run_id: str
    quality: QualityProfile
    patterns: PatternResult
    backtest: BacktestResult
    forecast: ForecastResult
    review: ReviewDecision
    interpretations: dict[str, Interpretation]
    chart_path: Path


def _text(inputs: BriefingInputs, step_id: str) -> tuple[str, ...]:
    interpretation = inputs.interpretations.get(step_id)
    return () if interpretation is None else (interpretation.summary, *interpretation.notes)


def _overview(inputs: BriefingInputs) -> SlideContent:
    quality, forecast = inputs.quality, inputs.forecast
    return SlideContent(
        title="Muster- und Prognose-Briefing",
        bullets=(
            f"Daten: {quality.start} bis {quality.end}, {quality.frequency_label}",
            f"Prognose: {forecast.horizon} Perioden ab {forecast.points[0].date}, Modell {forecast.model}",
            "Modell schlägt saisonal-naive Referenz: " + ("ja" if forecast.beats_baseline else "nein"),
            f"Lauf {inputs.run_id}",
        ),
    )


def _data_slide(inputs: BriefingInputs) -> SlideContent:
    quality = inputs.quality
    table = (
        ("Kennzahl", "Wert"),
        ("Gültige Beobachtungen", str(quality.valid_observations)),
        ("Volle Saisonzyklen", german_number(quality.full_seasonal_cycles, 1)),
        ("Fehlanteil", german_percent(quality.missing_share)),
        ("Doppelte Datumswerte", str(quality.duplicate_dates)),
    )
    return SlideContent(title="Datenlage", bullets=_text(inputs, "01_quality"), table=table)


def _pattern_slide(inputs: BriefingInputs) -> SlideContent:
    patterns = inputs.patterns
    table = (
        ("Kennzahl", "Wert"),
        (
            "Trend",
            f"{patterns.trend_direction} ({german_number(patterns.trend_slope_per_period)} pro Periode)",
        ),
        ("Saisonstärke (0–1)", german_number(patterns.seasonal_strength)),
        ("Saisonhoch / -tief", f"wie {patterns.peak_example_date} / wie {patterns.trough_example_date}"),
        ("Auffälligkeiten", str(len(patterns.anomalies))),
    )
    return SlideContent(
        title="Trend, Saisonalität, Auffälligkeiten", bullets=_text(inputs, "04_patterns"), table=table
    )


def _backtest_slide(inputs: BriefingInputs) -> SlideContent:
    header = ("Modell", "MASE", "sMAPE", "Abdeckung 80 %", "Abdeckung 95 %")
    rows = tuple(
        (
            score.model,
            german_number(score.mean_mase, 3),
            german_number(score.mean_smape),
            german_percent(score.mean_coverage_80),
            german_percent(score.mean_coverage_95),
        )
        for score in inputs.backtest.models
    )
    bullets = (*_text(inputs, "05_backtest")[:2], *_text(inputs, "06_forecast")[:2])
    return SlideContent(title="Modellvergleich im Backtest", bullets=bullets, table=(header, *rows))


def _forecast_slide(inputs: BriefingInputs) -> SlideContent:
    first, last = inputs.forecast.points[0], inputs.forecast.points[-1]
    bullets = (
        f"{first.date}: {german_number(first.point)} (95 %: {german_number(first.lower_95)} – "
        f"{german_number(first.upper_95)})",
        f"{last.date}: {german_number(last.point)} (95 %: {german_number(last.lower_95)} – "
        f"{german_number(last.upper_95)})",
        *_text(inputs, "07_visualize")[:3],
    )
    return SlideContent(title="Prognose mit Unsicherheitsband", bullets=bullets, image=inputs.chart_path)


def _closing_slide(inputs: BriefingInputs) -> SlideContent:
    review = f"Freigegeben am {inputs.review.decided_at[:10]}" + (
        f": {inputs.review.comment}" if inputs.review.comment else ""
    )
    return SlideContent(title="Kernaussagen", bullets=(*_text(inputs, "10_export"), review))


def build_slides(inputs: BriefingInputs) -> list[SlideContent]:
    return [
        _overview(inputs),
        _data_slide(inputs),
        _pattern_slide(inputs),
        _backtest_slide(inputs),
        _forecast_slide(inputs),
        _closing_slide(inputs),
    ]
