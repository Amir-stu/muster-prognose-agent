"""Runs the steps in diagram order, passes outputs via files, and implements both loops and the review gate.

State lives in runs/<run_id>/state.json and is written after every step, so a crashed run resumes where
it stopped. Each loop iteration writes into its own folder (iter_01, iter_02, ...).
"""

import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from prognose.config import Config, RunConfig, load_config
from prognose.intake import normalize_file
from prognose.interpreter import (
    InterpretationOutcome,
    InterpretationPending,
    Interpreter,
    accept_answer,
    validate_interpretation,
)
from prognose.pipeline import TOOLS, StepContext, read_model, write_model
from prognose.schemas import (
    DataMapping,
    GateResult,
    Handover,
    Interpretation,
    IterationTarget,
    ReviewDecision,
    RunState,
    StepRecord,
)
from prognose.steps import StepDefinition

ANALYSIS_STEPS = ("01_quality", "02_gate")
DATA_REQUEST_STEPS = ("03_data_request",)
MODELLING_STEPS = ("04_patterns", "05_backtest", "06_forecast", "07_visualize")
EXPORT_STEPS = ("10_export",)
STATE_FILE = "state.json"
TARGET_FILE = "ziel.json"
CONFIG_FILE = "config.toml"
APPROVED = "freigegeben"
STORED_DATE_FORMAT = "%Y-%m-%d"
RUNS_GITIGNORE = "*\n"


class OrchestratorError(RuntimeError):
    """The requested action does not fit the run's current state."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def iteration_dir(run_dir: Path, iteration: int) -> Path:
    return run_dir / f"iter_{iteration:02d}"


def load_state(run_dir: Path) -> RunState:
    return read_model(run_dir / STATE_FILE, RunState)


def save_state(run_dir: Path, state: RunState) -> RunState:
    write_model(run_dir / STATE_FILE, state)
    return state


def _require_status(state: RunState, *allowed: str) -> None:
    if state.status not in allowed:
        raise OrchestratorError(
            f"Lauf {state.run_id} hat Status {state.status}, erwartet: {', '.join(allowed)}"
        )


def _store_data(
    run_dir: Path, data_file: Path, iteration: int, mapping: DataMapping | None, run_config: RunConfig
) -> str:
    """Keep the run's own copy: the raw file as is, or the single mapped series as CSV."""
    suffix = ".csv" if mapping else data_file.suffix.lower()
    target = run_dir / "input" / f"daten_iter{iteration:02d}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if mapping is None:
        shutil.copyfile(data_file, target)
    else:
        series = normalize_file(data_file, mapping, run_config.date_column, run_config.value_column)
        series.to_csv(target, index=False, date_format=STORED_DATE_FORMAT)
    return target.relative_to(run_dir).as_posix()


def _open_iteration(run_dir: Path, state: RunState) -> None:
    folder = iteration_dir(run_dir, state.iteration)
    folder.mkdir(parents=True, exist_ok=True)
    write_model(
        folder / TARGET_FILE,
        IterationTarget(iteration=state.iteration, horizon=state.horizon, data_file=state.data_file),
    )


def _documents(step: StepDefinition, folder: Path) -> dict[str, str]:
    missing = [name for name in step.inputs if not (folder / name).is_file()]
    if missing:
        raise OrchestratorError(f"{step.step_id}: Eingaben fehlen: {', '.join(missing)}")
    return {name: (folder / name).read_text(encoding="utf-8") for name in step.inputs}


def _interpretation_file(folder: Path, step_id: str) -> Path:
    return folder / f"{step_id}.interpretation.json"


def _interpret(
    step: StepDefinition, folder: Path, interpreter: Interpreter, state: RunState
) -> InterpretationOutcome:
    submitted = _interpretation_file(folder, step.step_id)
    if state.pending_step == step.step_id and submitted.is_file():
        return InterpretationOutcome(read_model(submitted, Interpretation), 0.0)
    documents: Mapping[str, str] = _documents(step, folder)
    outcome = interpreter.interpret(step, documents)
    validate_interpretation(step.step_id, outcome.interpretation, documents)
    write_model(submitted, outcome.interpretation)
    return outcome


def _execute(
    run_dir: Path, state: RunState, step: StepDefinition, config: Config, interpreter: Interpreter
) -> RunState:
    folder = iteration_dir(run_dir, state.iteration)
    context = StepContext(run_dir=run_dir, iter_dir=folder, config=config, state=state)
    tool = TOOLS[step.tool]
    cost = 0.0
    if step.kind == "gate":
        tool(context, None)
    elif step.llm_first:
        outcome = _interpret(step, folder, interpreter, state)
        tool(context, outcome.interpretation)
        cost = outcome.cost_usd
    else:
        if state.pending_step != step.step_id:
            tool(context, None)
        cost = _interpret(step, folder, interpreter, state).cost_usd
    record = StepRecord(step=step.step_id, iteration=state.iteration, finished_at=_now(), cost_usd=cost)
    return save_state(
        run_dir,
        state.model_copy(
            update={
                "completed_steps": [*state.completed_steps, step.step_id],
                "history": [*state.history, record],
                "cost_usd": round(state.cost_usd + cost, 4),
                "pending_step": None,
            }
        ),
    )


def _pause_for_text(run_dir: Path, state: RunState, step_id: str, request: str) -> None:
    folder = iteration_dir(run_dir, state.iteration)
    (folder / f"{step_id}.request.md").write_text(request, encoding="utf-8")
    save_state(
        run_dir, state.model_copy(update={"status": "awaiting_interpretation", "pending_step": step_id})
    )


def _run_steps(
    run_dir: Path,
    state: RunState,
    step_ids: tuple[str, ...],
    steps: Mapping[str, StepDefinition],
    interpreter: Interpreter,
) -> RunState:
    config = load_config(run_dir / CONFIG_FILE)
    current = state
    for step_id in step_ids:
        if step_id in current.completed_steps:
            continue
        try:
            current = _execute(run_dir, current, steps[step_id], config, interpreter)
        except InterpretationPending as pending:
            _pause_for_text(run_dir, current, step_id, pending.request)
            raise
        except Exception as error:
            message = str(error) if str(error).startswith(step_id) else f"{step_id}: {error}"
            save_state(run_dir, current.model_copy(update={"status": "failed", "error": message}))
            raise
    return current


def _with_status(run_dir: Path, state: RunState, status: str) -> RunState:
    return save_state(run_dir, state.model_copy(update={"status": status}))


def _continue(
    run_dir: Path, running: RunState, steps: Mapping[str, StepDefinition], interpreter: Interpreter
) -> RunState:
    review_file = iteration_dir(run_dir, running.iteration) / "08_review.json"
    approved = review_file.is_file() and read_model(review_file, ReviewDecision).decision == APPROVED
    if not approved:
        return advance(run_dir, steps=steps, interpreter=interpreter)
    exported = _run_steps(run_dir, running, EXPORT_STEPS, steps, interpreter)
    return _with_status(run_dir, exported, "completed")


def resume(run_dir: Path, *, steps: Mapping[str, StepDefinition], interpreter: Interpreter) -> RunState:
    """Continue a failed run at the step that failed; finished steps are not repeated."""
    state = load_state(run_dir)
    _require_status(state, "failed")
    running = save_state(run_dir, state.model_copy(update={"status": "running", "error": None}))
    return _continue(run_dir, running, steps, interpreter)


def submit_interpretation(
    run_dir: Path, answer: Any, *, steps: Mapping[str, StepDefinition], interpreter: Interpreter
) -> RunState:
    """Accept the host's text for the paused step and continue; a rejected text leaves the run paused."""
    state = load_state(run_dir)
    _require_status(state, "awaiting_interpretation")
    step = steps[state.pending_step]
    folder = iteration_dir(run_dir, state.iteration)
    interpretation = accept_answer(step.step_id, answer, _documents(step, folder))
    write_model(_interpretation_file(folder, step.step_id), interpretation)
    running = save_state(run_dir, state.model_copy(update={"status": "running"}))
    return _continue(run_dir, running, steps, interpreter)


def advance(run_dir: Path, *, steps: Mapping[str, StepDefinition], interpreter: Interpreter) -> RunState:
    """Run the analysis part of the current iteration up to the next human decision."""
    state = load_state(run_dir)
    _require_status(state, "running")
    state = _run_steps(run_dir, state, ANALYSIS_STEPS, steps, interpreter)
    gate = read_model(iteration_dir(run_dir, state.iteration) / "02_gate.json", GateResult)
    if not gate.sufficient:
        state = _run_steps(run_dir, state, DATA_REQUEST_STEPS, steps, interpreter)
        return _with_status(run_dir, state, "waiting_for_data")
    state = _run_steps(run_dir, state, MODELLING_STEPS, steps, interpreter)
    return _with_status(run_dir, state, "awaiting_review")


def _stored_first_data(
    run_dir: Path, data_file: Path, mapping: DataMapping | None, run_config: RunConfig
) -> str:
    try:
        return _store_data(run_dir, data_file, 1, mapping, run_config)
    except (ValueError, OSError):
        shutil.rmtree(run_dir)
        raise


def create_run(
    *,
    runs_root: Path,
    data_file: Path,
    config_path: Path,
    horizon: int | None,
    llm_enabled: bool,
    host: Literal["claude", "copilot"] = "claude",
    mapping: DataMapping | None = None,
) -> Path:
    """Create the run folder with copies of data and config; returns the run folder."""
    config = load_config(config_path)
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    run_dir = runs_root.resolve() / run_id
    run_dir.mkdir(parents=True)
    (run_dir / ".gitignore").write_text(RUNS_GITIGNORE, encoding="utf-8")
    shutil.copyfile(config_path, run_dir / CONFIG_FILE)
    state = save_state(
        run_dir,
        RunState(
            run_id=run_id,
            status="running",
            iteration=1,
            data_file=_stored_first_data(run_dir, data_file, mapping, config.run),
            horizon=horizon or config.run.default_horizon,
            llm_enabled=llm_enabled,
            completed_steps=[],
            history=[],
            cost_usd=0.0,
            error=None,
            host=host,
            data_mapping=mapping,
        ),
    )
    _open_iteration(run_dir, state)
    return run_dir


def start_run(
    *,
    runs_root: Path,
    data_file: Path,
    config_path: Path,
    horizon: int | None,
    steps: Mapping[str, StepDefinition],
    interpreter: Interpreter,
    llm_enabled: bool,
) -> RunState:
    run_dir = create_run(
        runs_root=runs_root,
        data_file=data_file,
        config_path=config_path,
        horizon=horizon,
        llm_enabled=llm_enabled,
    )
    return advance(run_dir, steps=steps, interpreter=interpreter)


def _next_iteration(
    run_dir: Path,
    state: RunState,
    *,
    reason: str,
    data_file: Path | None,
    horizon: int | None,
    comment: str,
    steps: Mapping[str, StepDefinition],
    interpreter: Interpreter,
) -> RunState:
    config = load_config(run_dir / CONFIG_FILE)
    limit_reached = state.iteration >= config.run.max_iterations
    new_data = state.data_file
    if data_file is not None and not limit_reached:
        new_data = _store_data(run_dir, data_file, state.iteration + 1, state.data_mapping, config.run)
    new_horizon = horizon or state.horizon
    recorded_data = str(data_file) if data_file is not None and limit_reached else new_data
    write_model(
        iteration_dir(run_dir, state.iteration) / "09_handover.json",
        Handover(
            reason=reason,
            data_file=recorded_data,
            horizon=new_horizon,
            comment=comment,
            handed_over_at=_now(),
        ),
    )
    if limit_reached:
        return _with_status(run_dir, state, "stopped_max_loops")
    next_state = save_state(
        run_dir,
        state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "data_file": new_data,
                "horizon": new_horizon,
                "completed_steps": [],
                "status": "running",
                "error": None,
            }
        ),
    )
    _open_iteration(run_dir, next_state)
    return advance(run_dir, steps=steps, interpreter=interpreter)


def review(
    run_dir: Path,
    *,
    decision: str,
    comment: str,
    steps: Mapping[str, StepDefinition],
    interpreter: Interpreter,
    data_file: Path | None = None,
    horizon: int | None = None,
) -> RunState:
    """Step 08 (Deine Prüfung): approve → export (10), adjust → hand over (09) and restart at 01."""
    state = load_state(run_dir)
    _require_status(state, "awaiting_review")
    record = ReviewDecision(decision=decision, comment=comment, decided_at=_now())
    write_model(iteration_dir(run_dir, state.iteration) / "08_review.json", record)
    if record.decision != APPROVED:
        return _next_iteration(
            run_dir,
            state,
            reason="anpassung",
            data_file=data_file,
            horizon=horizon,
            comment=comment,
            steps=steps,
            interpreter=interpreter,
        )
    running = _with_status(run_dir, state, "running")
    exported = _run_steps(run_dir, running, EXPORT_STEPS, steps, interpreter)
    return _with_status(run_dir, exported, "completed")


def handover(
    run_dir: Path,
    *,
    data_file: Path | None,
    horizon: int | None,
    comment: str,
    steps: Mapping[str, StepDefinition],
    interpreter: Interpreter,
) -> RunState:
    """Step 09 after the "Nein" branch: new data arrives and the run restarts at 01."""
    state = load_state(run_dir)
    _require_status(state, "waiting_for_data")
    if data_file is None:
        raise OrchestratorError("Für die Übergabe nach einer Datenanforderung ist eine neue Datei nötig")
    return _next_iteration(
        run_dir,
        state,
        reason="daten_nachgefordert",
        data_file=data_file,
        horizon=horizon,
        comment=comment,
        steps=steps,
        interpreter=interpreter,
    )
