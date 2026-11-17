"""Command line: prognose synth | run | review | handover | status."""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from prognose import DEFAULT_CONFIG_PATH, DEFAULT_RUNS_DIR, STEPS_DIR
from prognose.config import load_config
from prognose.interpreter import ClaudeInterpreter, Interpreter, StepRejected, TemplateInterpreter
from prognose.orchestrator import (
    CONFIG_FILE,
    OrchestratorError,
    advance,
    create_run,
    handover,
    iteration_dir,
    load_state,
    resume,
    review,
)
from prognose.runner import AgentError
from prognose.schemas import RunState
from prognose.steps import load_steps
from prognose.synthetic import SyntheticSpec, make_series

SANDBOX_DIR_NAME = ".agent_sandbox"
EXPECTED_ERRORS = (OrchestratorError, StepRejected, AgentError, ValueError, FileNotFoundError, KeyError)

NEXT_STEP_HINTS = {
    "waiting_for_data": "Zu wenig oder fehlerhafte Daten. Datenanforderung: {folder}/03_data_request.md\n"
    "Weiter mit: prognose handover {run_id} --data <neue-datei>",
    "awaiting_review": "Prognose wartet auf Ihre Prüfung. Grafik: {folder}/07_chart.png\n"
    "Freigeben: prognose review {run_id} --approve\n"
    'Anpassen:  prognose review {run_id} --adjust "<was ändern>" [--horizon N] [--data <datei>]',
    "completed": "Fertig. Excel: {folder}/10_report.xlsx\nPowerPoint: {folder}/10_briefing.pptx",
    "stopped_max_loops": "Schleifenlimit erreicht, Lauf beendet. Neu starten: prognose run --data <datei>",
    "failed": "Lauf fehlgeschlagen: {error}\nFortsetzen: prognose resume {run_id}",
    "running": "Lauf läuft noch oder wurde unterbrochen.",
}


def _interpreter(llm_enabled: bool, run_dir: Path) -> Interpreter:
    if not llm_enabled:
        return TemplateInterpreter()
    return ClaudeInterpreter(
        llm=load_config(run_dir / CONFIG_FILE).llm, sandbox_dir=run_dir / SANDBOX_DIR_NAME
    )


def _report(state: RunState, runs_root: Path) -> None:
    folder = iteration_dir(runs_root / state.run_id, state.iteration)
    print(NEXT_STEP_HINTS[state.status].format(folder=folder, run_id=state.run_id, error=state.error))
    summary = {
        "run_id": state.run_id,
        "status": state.status,
        "iteration": state.iteration,
        "horizon": state.horizon,
        "llm": state.llm_enabled,
        "cost_usd": state.cost_usd,
        "run_dir": str(runs_root / state.run_id),
        "error": state.error,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _synth(args: argparse.Namespace) -> None:
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    make_series(SyntheticSpec(periods=args.periods, seed=args.seed, anomaly_positions=(30, 55))).to_csv(
        out, index=False
    )
    print(f"Synthetische Reihe geschrieben: {out}")


def _run(args: argparse.Namespace) -> RunState:
    run_dir = create_run(
        runs_root=Path(args.runs_dir).resolve(),
        data_file=Path(args.data).resolve(),
        config_path=Path(args.config).resolve(),
        horizon=args.horizon,
        llm_enabled=not args.no_llm,
    )
    print(f"Lauf angelegt: {run_dir}")
    return advance(run_dir, steps=load_steps(STEPS_DIR), interpreter=_interpreter(not args.no_llm, run_dir))


def _existing_run(args: argparse.Namespace) -> tuple[Path, Interpreter]:
    run_dir = Path(args.runs_dir).resolve() / args.run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Lauf nicht gefunden: {run_dir}")
    llm_enabled = load_state(run_dir).llm_enabled and not args.no_llm
    return run_dir, _interpreter(llm_enabled, run_dir)


def _optional_path(value: str | None) -> Path | None:
    return Path(value).resolve() if value else None


def _review(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    decision = "freigegeben" if args.approve else "anpassen"
    comment = args.comment or (args.adjust or "")
    return review(
        run_dir,
        decision=decision,
        comment=comment,
        steps=load_steps(STEPS_DIR),
        interpreter=interpreter,
        data_file=_optional_path(args.data),
        horizon=args.horizon,
    )


def _handover(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    return handover(
        run_dir,
        data_file=_optional_path(args.data),
        horizon=args.horizon,
        comment=args.comment or "",
        steps=load_steps(STEPS_DIR),
        interpreter=interpreter,
    )


def _resume(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    return resume(run_dir, steps=load_steps(STEPS_DIR), interpreter=interpreter)


def _status(args: argparse.Namespace) -> RunState:
    return load_state(Path(args.runs_dir).resolve() / args.run_id)


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--no-llm", action="store_true", help="Nur Werkzeuge, Vorlagentext statt Subagent")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prognose", description="Muster- und Prognose-Agent")
    commands = parser.add_subparsers(dest="command", required=True)

    synth = commands.add_parser("synth", help="Synthetische Testreihe erzeugen")
    synth.add_argument("--out", required=True)
    synth.add_argument("--periods", type=int, default=72)
    synth.add_argument("--seed", type=int, default=7)

    run = commands.add_parser("run", help="Neuen Lauf starten")
    run.add_argument("--data", required=True)
    run.add_argument("--horizon", type=int)
    run.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    _add_run_options(run)

    review_parser = commands.add_parser("review", help="Schritt 08: Prognose freigeben oder anpassen")
    review_parser.add_argument("run_id")
    choice = review_parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--approve", action="store_true")
    choice.add_argument("--adjust", metavar="TEXT")
    review_parser.add_argument("--comment")
    review_parser.add_argument("--data")
    review_parser.add_argument("--horizon", type=int)
    _add_run_options(review_parser)

    handover_parser = commands.add_parser("handover", help="Schritt 09: neue Daten übergeben")
    handover_parser.add_argument("run_id")
    handover_parser.add_argument("--data", required=True)
    handover_parser.add_argument("--horizon", type=int)
    handover_parser.add_argument("--comment")
    _add_run_options(handover_parser)

    resume_parser = commands.add_parser("resume", help="Fehlgeschlagenen Lauf fortsetzen")
    resume_parser.add_argument("run_id")
    _add_run_options(resume_parser)

    status = commands.add_parser("status", help="Status eines Laufs anzeigen")
    status.add_argument("run_id")
    status.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    return parser


HANDLERS: dict[str, Callable[[argparse.Namespace], RunState]] = {
    "run": _run,
    "review": _review,
    "handover": _handover,
    "resume": _resume,
    "status": _status,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "synth":
        _synth(args)
        return 0
    try:
        state = HANDLERS[args.command](args)
    except EXPECTED_ERRORS as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1
    _report(state, Path(args.runs_dir).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
