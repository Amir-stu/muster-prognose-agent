"""Integration tests of the full pipeline in --no-llm mode (template interpretations, real tools)."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pptx import Presentation

from prognose.interpreter import InterpretationOutcome, StepRejected, TemplateInterpreter
from prognose.orchestrator import (
    OrchestratorError,
    advance,
    handover,
    load_state,
    resume,
    review,
    save_state,
    start_run,
)
from prognose.schemas import Interpretation
from prognose.steps import load_steps
from prognose.synthetic import SyntheticSpec, make_series


def _csv(tmp_path: Path, name: str, periods: int) -> Path:
    path = tmp_path / name
    make_series(SyntheticSpec(periods=periods, anomaly_positions=(30,) if periods > 30 else ())).to_csv(
        path, index=False
    )
    return path


@pytest.fixture
def pipeline(tmp_path, steps_dir, config_path):
    steps = load_steps(steps_dir)

    def start(periods=72, horizon=12, config=config_path, interpreter=None):
        return start_run(
            runs_root=tmp_path / "runs",
            data_file=_csv(tmp_path, f"reihe_{periods}.csv", periods),
            config_path=config,
            horizon=horizon,
            steps=steps,
            interpreter=interpreter or TemplateInterpreter(),
            llm_enabled=False,
        )

    return start, steps


def _run_dir(tmp_path, state):
    return tmp_path / "runs" / state.run_id


def test_happy_path_stops_for_review_then_exports(tmp_path, pipeline):
    start, steps = pipeline
    state = start()
    run_dir = _run_dir(tmp_path, state)
    iteration = run_dir / "iter_01"
    assert state.status == "awaiting_review"
    for name in (
        "01_quality.json",
        "02_gate.json",
        "04_patterns.json",
        "05_backtest.json",
        "06_forecast.json",
        "07_chart.png",
        "07_visualize.json",
        "06_forecast.interpretation.json",
    ):
        assert (iteration / name).is_file(), name
    assert not list(iteration.glob("10_*"))

    final = review(
        run_dir, decision="freigegeben", comment="passt", steps=steps, interpreter=TemplateInterpreter()
    )
    assert final.status == "completed"
    forecast = json.loads((iteration / "06_forecast.json").read_text(encoding="utf-8"))
    sheet = load_workbook(iteration / "10_report.xlsx")["Prognose"]
    excel_points = [row[1] for row in sheet.iter_rows(min_row=2, values_only=True)]
    assert excel_points == [point["point"] for point in forecast["points"]]
    assert len(Presentation(str(iteration / "10_briefing.pptx")).slides) == 6
    assert json.loads((iteration / "08_review.json").read_text(encoding="utf-8"))["decision"] == "freigegeben"


def test_short_series_takes_nein_branch_then_handover_recovers(tmp_path, pipeline):
    start, steps = pipeline
    state = start(periods=12)
    run_dir = _run_dir(tmp_path, state)
    assert state.status == "waiting_for_data"
    request = (run_dir / "iter_01" / "03_data_request.md").read_text(encoding="utf-8")
    assert "beobachtungen" in request and "saisonzyklen" in request
    assert not (run_dir / "iter_01" / "04_patterns.json").exists()

    resumed = handover(
        run_dir,
        data_file=_csv(tmp_path, "mehr.csv", 60),
        horizon=None,
        comment="neue Daten",
        steps=steps,
        interpreter=TemplateInterpreter(),
    )
    assert resumed.status == "awaiting_review"
    assert resumed.iteration == 2
    assert (run_dir / "iter_01" / "09_handover.json").is_file()
    assert (run_dir / "iter_02" / "06_forecast.json").is_file()


def test_adjust_restarts_with_new_horizon(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start())
    state = review(
        run_dir,
        decision="anpassen",
        comment="nur 6 Monate",
        horizon=6,
        steps=steps,
        interpreter=TemplateInterpreter(),
    )
    assert state.status == "awaiting_review"
    assert state.iteration == 2
    forecast = json.loads((run_dir / "iter_02" / "06_forecast.json").read_text(encoding="utf-8"))
    assert forecast["horizon"] == 6
    assert len(forecast["points"]) == 6


def test_loop_limit_stops_run(tmp_path, pipeline, config_path):
    start, steps = pipeline
    limited = tmp_path / "config.toml"
    limited.write_text(
        config_path.read_text(encoding="utf-8").replace("max_iterations = 3", "max_iterations = 2"),
        encoding="utf-8",
    )
    run_dir = _run_dir(tmp_path, start(config=limited))
    review(run_dir, decision="anpassen", comment="a", steps=steps, interpreter=TemplateInterpreter())
    state = review(run_dir, decision="anpassen", comment="b", steps=steps, interpreter=TemplateInterpreter())
    assert state.status == "stopped_max_loops"
    assert state.iteration == 2


def test_review_when_not_awaiting_review_raises(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start(periods=12))
    with pytest.raises(OrchestratorError, match="waiting_for_data"):
        review(run_dir, decision="freigegeben", comment="", steps=steps, interpreter=TemplateInterpreter())


def test_handover_when_awaiting_review_raises(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start())
    with pytest.raises(OrchestratorError):
        handover(
            run_dir, data_file=None, horizon=6, comment="", steps=steps, interpreter=TemplateInterpreter()
        )


def test_resume_runs_only_missing_steps(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start())
    iteration = run_dir / "iter_01"
    backtest_mtime = (iteration / "05_backtest.json").stat().st_mtime_ns
    (iteration / "07_visualize.json").unlink()
    state = load_state(run_dir)
    save_state(
        run_dir,
        state.model_copy(
            update={
                "status": "running",
                "completed_steps": [s for s in state.completed_steps if s != "07_visualize"],
            }
        ),
    )
    resumed = advance(run_dir, steps=steps, interpreter=TemplateInterpreter())
    assert resumed.status == "awaiting_review"
    assert (iteration / "07_visualize.json").is_file()
    assert (iteration / "05_backtest.json").stat().st_mtime_ns == backtest_mtime


@dataclass(frozen=True)
class InventingInterpreter:
    def interpret(self, step, documents):
        return InterpretationOutcome(
            Interpretation(summary="Umsatz steigt auf 98765 Einheiten.", notes=[]), 0.0
        )


@dataclass(frozen=True)
class RejectingInterpreter:
    def interpret(self, step, documents):
        raise StepRejected(f"{step.step_id}: abgelehnt")


@pytest.mark.parametrize("interpreter", [InventingInterpreter(), RejectingInterpreter()])
def test_unbacked_numbers_fail_the_run(tmp_path, pipeline, interpreter):
    start, _ = pipeline
    with pytest.raises(StepRejected):
        start(interpreter=interpreter)
    run_dir = next((tmp_path / "runs").iterdir())
    state = load_state(run_dir)
    assert state.status == "failed"
    assert "01_quality" in state.error


def test_advance_when_not_running_raises(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start())
    with pytest.raises(OrchestratorError):
        advance(run_dir, steps=steps, interpreter=TemplateInterpreter())


def test_resume_after_failed_analysis_continues_to_review(tmp_path, pipeline):
    start, steps = pipeline
    with pytest.raises(StepRejected):
        start(interpreter=RejectingInterpreter())
    run_dir = next((tmp_path / "runs").iterdir())
    state = resume(run_dir, steps=steps, interpreter=TemplateInterpreter())
    assert state.status == "awaiting_review"
    assert state.error is None


def test_resume_after_failed_export_finishes_export(tmp_path, pipeline):
    start, steps = pipeline
    run_dir = _run_dir(tmp_path, start())
    review(run_dir, decision="freigegeben", comment="", steps=steps, interpreter=TemplateInterpreter())
    state = load_state(run_dir)
    remaining = [step for step in state.completed_steps if step != "10_export"]
    save_state(run_dir, state.model_copy(update={"status": "failed", "completed_steps": remaining}))
    assert resume(run_dir, steps=steps, interpreter=TemplateInterpreter()).status == "completed"


def test_resume_when_not_failed_raises(tmp_path, pipeline):
    start, steps = pipeline
    with pytest.raises(OrchestratorError, match="failed"):
        resume(_run_dir(tmp_path, start()), steps=steps, interpreter=TemplateInterpreter())
