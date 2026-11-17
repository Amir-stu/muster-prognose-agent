"""Tool adapters: read inputs from the iteration folder, run a deterministic tool, write the output.

Every adapter has the signature (StepContext, Interpretation | None) -> None. Only steps that run their
subagent first (03, 10) receive an interpretation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from prognose.config import Config
from prognose.schemas import (
    BacktestResult,
    ExportResult,
    ForecastResult,
    GateResult,
    Interpretation,
    PatternResult,
    QualityProfile,
    ReviewDecision,
    RunState,
    VizResult,
)
from prognose.tools.backtest import run_backtest
from prognose.tools.briefing import BriefingInputs, build_slides
from prognose.tools.export_excel import write_workbook
from prognose.tools.export_pptx import write_briefing
from prognose.tools.forecast import make_forecast
from prognose.tools.patterns import detect_patterns
from prognose.tools.plot import render_chart
from prognose.tools.profile import prepare_series, profile_series
from prognose.tools.sufficiency import evaluate_sufficiency

EXCEL_SUFFIXES = (".xlsx", ".xls")
INTERPRETED_STEPS = ("01_quality", "04_patterns", "05_backtest", "06_forecast", "07_visualize")


@dataclass(frozen=True)
class StepContext:
    run_dir: Path
    iter_dir: Path
    config: Config
    state: RunState

    @property
    def data_path(self) -> Path:
        return self.run_dir / self.state.data_file


def write_model(path: Path, model: BaseModel) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def read_model[ModelT: BaseModel](path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def load_table(path: Path) -> pd.DataFrame:
    return pd.read_excel(path) if path.suffix.lower() in EXCEL_SUFFIXES else pd.read_csv(path)


def _prepared_series(ctx: StepContext) -> tuple[pd.Series, QualityProfile]:
    quality = read_model(ctx.iter_dir / "01_quality.json", QualityProfile)
    run = ctx.config.run
    return prepare_series(load_table(ctx.data_path), quality, run.date_column, run.value_column), quality


def quality_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    run = ctx.config.run
    write_model(
        ctx.iter_dir / "01_quality.json",
        profile_series(load_table(ctx.data_path), run.date_column, run.value_column),
    )


def gate_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    quality = read_model(ctx.iter_dir / "01_quality.json", QualityProfile)
    write_model(ctx.iter_dir / "02_gate.json", evaluate_sufficiency(quality, ctx.config.gate))


def data_request_tool(ctx: StepContext, interpretation: Interpretation | None) -> None:
    gate = read_model(ctx.iter_dir / "02_gate.json", GateResult)
    failed = [rule for rule in gate.rules if not rule.passed]
    rows = [
        f"| {rule.rule} | {rule.description} | {rule.value:g} | {rule.comparison} {rule.threshold:g} |"
        for rule in failed
    ]
    summary = interpretation.summary if interpretation else ""
    notes = [f"- {note}" for note in (interpretation.notes if interpretation else [])]
    lines = [
        f"# Datenanforderung – Lauf {ctx.state.run_id}, Iteration {ctx.state.iteration}",
        "",
        summary,
        "",
        "## Nicht erfüllte Regeln",
        "",
        "| Regel | Beschreibung | Ist-Wert | Anforderung |",
        "|---|---|---|---|",
        *rows,
        "",
        "## Hinweise",
        "",
        *notes,
        "",
        "## Nächster Schritt",
        "",
        f"`prognose handover {ctx.state.run_id} --data <neue-datei>`",
        "",
    ]
    (ctx.iter_dir / "03_data_request.md").write_text("\n".join(lines), encoding="utf-8")


def patterns_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    series, quality = _prepared_series(ctx)
    write_model(
        ctx.iter_dir / "04_patterns.json", detect_patterns(series, quality.season_period, ctx.config.patterns)
    )


def backtest_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    series, quality = _prepared_series(ctx)
    result = run_backtest(series, quality.season_period, ctx.state.horizon, ctx.config.backtest)
    write_model(ctx.iter_dir / "05_backtest.json", result)


def forecast_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    series, quality = _prepared_series(ctx)
    backtest = read_model(ctx.iter_dir / "05_backtest.json", BacktestResult)
    result = make_forecast(series, backtest, ctx.state.horizon, quality.season_period)
    write_model(ctx.iter_dir / "06_forecast.json", result)


def visualize_tool(ctx: StepContext, _interpretation: Interpretation | None) -> None:
    series, _quality = _prepared_series(ctx)
    patterns = read_model(ctx.iter_dir / "04_patterns.json", PatternResult)
    forecast = read_model(ctx.iter_dir / "06_forecast.json", ForecastResult)
    chart = ctx.iter_dir / "07_chart.png"
    render_chart(
        series,
        forecast,
        patterns.anomalies,
        chart,
        f"{ctx.config.run.value_column}: Historie und Prognose ({forecast.model})",
    )
    write_model(
        ctx.iter_dir / "07_visualize.json",
        VizResult(
            chart_file=chart.name,
            history_points=len(series),
            forecast_points=len(forecast.points),
            anomaly_points=len(patterns.anomalies),
        ),
    )


def _interpretations(iter_dir: Path, current: Interpretation | None) -> dict[str, Interpretation]:
    stored = {
        step_id: read_model(iter_dir / f"{step_id}.interpretation.json", Interpretation)
        for step_id in INTERPRETED_STEPS
        if (iter_dir / f"{step_id}.interpretation.json").is_file()
    }
    return stored if current is None else {**stored, "10_export": current}


def export_tool(ctx: StepContext, interpretation: Interpretation | None) -> None:
    series, quality = _prepared_series(ctx)
    inputs = BriefingInputs(
        run_id=ctx.state.run_id,
        quality=quality,
        patterns=read_model(ctx.iter_dir / "04_patterns.json", PatternResult),
        backtest=read_model(ctx.iter_dir / "05_backtest.json", BacktestResult),
        forecast=read_model(ctx.iter_dir / "06_forecast.json", ForecastResult),
        review=read_model(ctx.iter_dir / "08_review.json", ReviewDecision),
        interpretations=_interpretations(ctx.iter_dir, interpretation),
        chart_path=ctx.iter_dir / "07_chart.png",
    )
    excel, pptx = ctx.iter_dir / "10_report.xlsx", ctx.iter_dir / "10_briefing.pptx"
    write_workbook(
        excel, series, quality, inputs.patterns, inputs.backtest, inputs.forecast, inputs.chart_path
    )
    slides = write_briefing(pptx, build_slides(inputs))
    write_model(
        ctx.iter_dir / "10_export.json",
        ExportResult(excel_file=excel.name, pptx_file=pptx.name, slides=slides),
    )


TOOLS: dict[str, Callable[[StepContext, Interpretation | None], None]] = {
    "profile": quality_tool,
    "sufficiency": gate_tool,
    "data_request": data_request_tool,
    "patterns": patterns_tool,
    "backtest": backtest_tool,
    "forecast": forecast_tool,
    "visualize": visualize_tool,
    "export": export_tool,
}
