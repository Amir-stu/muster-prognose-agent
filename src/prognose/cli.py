"""Command line: prognose synth | inspect | run | interpret | review | handover | resume | status."""

import argparse
import io
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from prognose import DEFAULT_CONFIG_PATH, DEFAULT_RUNS_DIR_NAME, STEPS_DIR
from prognose.config import load_config
from prognose.copilot_install import default_targets, install_agent
from prognose.intake import inspect_file
from prognose.interpreter import (
    ClaudeInterpreter,
    HostInterpreter,
    InterpretationPending,
    Interpreter,
    StepRejected,
    TemplateInterpreter,
)
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
    submit_interpretation,
)
from prognose.runner import AgentError
from prognose.schemas import DataMapping, RunState
from prognose.steps import load_steps
from prognose.synthetic import SyntheticSpec, make_series

SANDBOX_DIR_NAME = ".agent_sandbox"
EXPECTED_ERRORS = (OrchestratorError, AgentError, ValueError, FileNotFoundError, KeyError)
ERROR_EXIT_CODE = 1
REJECTED_EXIT_CODE = 2
ANSWER_ENCODING = "utf-8-sig"

NEXT_STEP_HINTS = {
    "awaiting_interpretation": "Text für Schritt {pending} nötig. Auftrag: {folder}/{pending}.request.md\n"
    "Einreichen: prognose interpret {run_id} --file <antwort.json>",
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


def _interpreter(llm_enabled: bool, run_dir: Path, host: str) -> Interpreter:
    if not llm_enabled:
        return TemplateInterpreter()
    if host == "copilot":
        return HostInterpreter()
    return ClaudeInterpreter(
        llm=load_config(run_dir / CONFIG_FILE).llm, sandbox_dir=run_dir / SANDBOX_DIR_NAME
    )


def _until_pause(run_dir: Path, action: Callable[[], RunState]) -> RunState:
    """A pause for host-written text is a normal outcome, reported like any other status."""
    try:
        return action()
    except InterpretationPending:
        return load_state(run_dir)


def _report(state: RunState, runs_root: Path) -> None:
    folder = iteration_dir(runs_root / state.run_id, state.iteration)
    hint = NEXT_STEP_HINTS[state.status].format(
        folder=folder, run_id=state.run_id, error=state.error, pending=state.pending_step
    )
    print(hint)
    paused = state.status == "awaiting_interpretation"
    summary = {
        "run_id": state.run_id,
        "status": state.status,
        "iteration": state.iteration,
        "horizon": state.horizon,
        "llm": state.llm_enabled,
        "cost_usd": state.cost_usd,
        "run_dir": str(runs_root / state.run_id),
        "iteration_dir": str(folder),
        "pending_step": state.pending_step if paused else None,
        "request_file": str(folder / f"{state.pending_step}.request.md") if paused else None,
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


def _parse_filters(pairs: Sequence[str]) -> dict[str, str]:
    malformed = [pair for pair in pairs if "=" not in pair]
    if malformed:
        raise ValueError(f"--filter erwartet Spalte=Wert, erhalten: {', '.join(malformed)}")
    return {key.strip(): value.strip() for key, value in (pair.split("=", 1) for pair in pairs)}


def _mapping(args: argparse.Namespace) -> DataMapping | None:
    details = (args.sheet, args.filter, args.decimal, args.date_order, args.aggregate != "keine")
    if not args.date_column and not args.value_column:
        if any(details):
            raise ValueError("Diese Optionen brauchen --date-column und --value-column")
        return None
    if not args.date_column or not args.value_column:
        raise ValueError("--date-column und --value-column gehören zusammen")
    return DataMapping(
        date_column=args.date_column,
        value_column=args.value_column,
        sheet=args.sheet,
        filters=_parse_filters(args.filter),
        aggregate=args.aggregate,
        decimal=args.decimal,
        date_order=args.date_order,
    )


def _run(args: argparse.Namespace) -> RunState:
    run_dir = create_run(
        runs_root=Path(args.runs_dir).resolve(),
        data_file=Path(args.data).resolve(),
        config_path=Path(args.config).resolve(),
        horizon=args.horizon,
        llm_enabled=not args.no_llm,
        host=args.host,
        mapping=_mapping(args),
    )
    print(f"Lauf angelegt: {run_dir}")
    interpreter = _interpreter(not args.no_llm, run_dir, args.host)
    return _until_pause(
        run_dir, lambda: advance(run_dir, steps=load_steps(STEPS_DIR), interpreter=interpreter)
    )


def _existing_run(args: argparse.Namespace) -> tuple[Path, Interpreter]:
    run_dir = Path(args.runs_dir).resolve() / args.run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Lauf nicht gefunden: {run_dir}")
    state = load_state(run_dir)
    return run_dir, _interpreter(state.llm_enabled and not args.no_llm, run_dir, state.host)


def _read_answer(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding=ANSWER_ENCODING))
    except json.JSONDecodeError as error:
        raise StepRejected(f"Antwort ist kein gültiges JSON: {error}") from error


def _interpret(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    answer = _read_answer(Path(args.file).resolve())
    return _until_pause(
        run_dir,
        lambda: submit_interpretation(run_dir, answer, steps=load_steps(STEPS_DIR), interpreter=interpreter),
    )


def _optional_path(value: str | None) -> Path | None:
    return Path(value).resolve() if value else None


def _review(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    decision = "freigegeben" if args.approve else "anpassen"
    comment = args.comment or (args.adjust or "")
    return _until_pause(
        run_dir,
        lambda: review(
            run_dir,
            decision=decision,
            comment=comment,
            steps=load_steps(STEPS_DIR),
            interpreter=interpreter,
            data_file=_optional_path(args.data),
            horizon=args.horizon,
        ),
    )


def _handover(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    return _until_pause(
        run_dir,
        lambda: handover(
            run_dir,
            data_file=_optional_path(args.data),
            horizon=args.horizon,
            comment=args.comment or "",
            steps=load_steps(STEPS_DIR),
            interpreter=interpreter,
        ),
    )


def _resume(args: argparse.Namespace) -> RunState:
    run_dir, interpreter = _existing_run(args)
    return _until_pause(
        run_dir, lambda: resume(run_dir, steps=load_steps(STEPS_DIR), interpreter=interpreter)
    )


def _status(args: argparse.Namespace) -> RunState:
    return load_state(Path(args.runs_dir).resolve() / args.run_id)


def _inspect(args: argparse.Namespace) -> None:
    print(json.dumps(inspect_file(Path(args.file).resolve(), args.sheet), indent=2, ensure_ascii=False))


def _install_copilot(_args: argparse.Namespace) -> None:
    for target in install_agent(sys.executable, default_targets()):
        print(f"Agent installiert: {target}")
    print("VS Code neu laden, dann im Copilot-Chat den Agenten 'Prognose' wählen.")


def _default_runs_dir() -> str:
    return str(Path.cwd() / DEFAULT_RUNS_DIR_NAME)


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-dir", default=_default_runs_dir())
    parser.add_argument("--no-llm", action="store_true", help="Nur Werkzeuge, Vorlagentext statt Subagent")


def _add_mapping_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date-column", help="Datumsspalte der Rohdatei")
    parser.add_argument("--value-column", help="Wertspalte der Rohdatei")
    parser.add_argument("--sheet", help="Tabellenblatt einer Excel-Datei")
    parser.add_argument("--filter", action="append", default=[], metavar="SPALTE=WERT")
    parser.add_argument("--aggregate", choices=("keine", "summe", "mittelwert"), default="keine")
    parser.add_argument("--decimal", choices=("komma", "punkt"))
    parser.add_argument("--date-order", choices=("tag_zuerst", "monat_zuerst"))


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
    run.add_argument("--host", choices=("claude", "copilot"), default="claude", help="Wer die Texte schreibt")
    _add_mapping_options(run)
    _add_run_options(run)

    inspect_parser = commands.add_parser("inspect", help="Struktur einer Datei anzeigen, ohne Messwerte")
    inspect_parser.add_argument("file")
    inspect_parser.add_argument("--sheet")

    interpret_parser = commands.add_parser("interpret", help="Text für den wartenden Schritt einreichen")
    interpret_parser.add_argument("run_id")
    interpret_parser.add_argument("--file", required=True)
    _add_run_options(interpret_parser)

    commands.add_parser("install-copilot", help="Agent 'Prognose' für GitHub Copilot installieren")

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
    status.add_argument("--runs-dir", default=_default_runs_dir())
    return parser


HANDLERS: dict[str, Callable[[argparse.Namespace], RunState]] = {
    "run": _run,
    "interpret": _interpret,
    "review": _review,
    "handover": _handover,
    "resume": _resume,
    "status": _status,
}
PLAIN_COMMANDS: dict[str, Callable[[argparse.Namespace], None]] = {
    "synth": _synth,
    "inspect": _inspect,
    "install-copilot": _install_copilot,
}


def _dispatch(args: argparse.Namespace) -> None:
    if args.command in PLAIN_COMMANDS:
        PLAIN_COMMANDS[args.command](args)
        return
    _report(HANDLERS[args.command](args), Path(args.runs_dir).resolve())


def main(argv: Sequence[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        _dispatch(args)
    except StepRejected as error:
        print(f"Abgelehnt: {error}", file=sys.stderr)
        return REJECTED_EXIT_CODE
    except EXPECTED_ERRORS as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return ERROR_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
