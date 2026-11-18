"""Copilot as host: the run pauses at each text step, and submitted text must pass the number check."""

import json
from pathlib import Path

import pytest

from prognose import STEPS_DIR
from prognose.cli import main
from prognose.copilot_install import install_agent, render_agent
from prognose.interpreter import HostInterpreter, StepRejected
from prognose.orchestrator import OrchestratorError, iteration_dir, load_state, submit_interpretation
from prognose.steps import load_steps

SAFE_TEXT = {"summary": "Der Schritt ist abgeschlossen.", "notes": []}


def _summary(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{") :])


def _start(tmp_path: Path, capsys, periods: int = 72) -> tuple[str, Path]:
    data, runs = tmp_path / "reihe.csv", tmp_path / "runs"
    main(["synth", "--out", str(data), "--periods", str(periods)])
    capsys.readouterr()
    assert main(["run", "--data", str(data), "--host", "copilot", "--runs-dir", str(runs)]) == 0
    return _summary(capsys)["run_id"], runs


def _answer(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "antwort.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _submit(run_id: str, runs: Path, tmp_path: Path, capsys) -> dict:
    answer = _answer(tmp_path, SAFE_TEXT)
    assert main(["interpret", run_id, "--file", str(answer), "--runs-dir", str(runs)]) == 0
    return _summary(capsys)


def _submit_until(status: str, run_id: str, runs: Path, tmp_path: Path, capsys) -> dict:
    summary = _submit(run_id, runs, tmp_path, capsys)
    while summary["status"] != status:
        assert summary["status"] == "awaiting_interpretation"
        summary = _submit(run_id, runs, tmp_path, capsys)
    return summary


def test_run_when_host_copilot_pauses_at_first_text_step(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    state = load_state(runs / run_id)
    request = iteration_dir(runs / run_id, 1) / "01_quality.request.md"
    assert state.status == "awaiting_interpretation"
    assert state.pending_step == "01_quality"
    assert "01_quality.json" in request.read_text(encoding="utf-8")


def test_interpret_when_text_invents_number_rejects_and_stays_paused(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    answer = _answer(tmp_path, {"summary": "Der Absatz steigt auf 98765 Einheiten.", "notes": []})
    assert main(["interpret", run_id, "--file", str(answer), "--runs-dir", str(runs)]) == 2
    assert "98765" in capsys.readouterr().err
    state = load_state(runs / run_id)
    assert state.status == "awaiting_interpretation"
    assert state.pending_step == "01_quality"


def test_interpret_when_answer_malformed_rejects_and_stays_paused(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    answer = _answer(tmp_path, {"text": "falsches Format"})
    assert main(["interpret", run_id, "--file", str(answer), "--runs-dir", str(runs)]) == 2
    assert load_state(runs / run_id).status == "awaiting_interpretation"


def test_submit_when_run_not_paused_raises(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    _submit_until("awaiting_review", run_id, runs, tmp_path, capsys)
    with pytest.raises(OrchestratorError, match="awaiting_review"):
        submit_interpretation(
            runs / run_id, SAFE_TEXT, steps=load_steps(STEPS_DIR), interpreter=HostInterpreter()
        )


def test_host_run_when_text_submitted_stops_at_human_review_before_export(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    summary = _submit_until("awaiting_review", run_id, runs, tmp_path, capsys)
    folder = iteration_dir(runs / run_id, 1)
    assert summary["status"] == "awaiting_review"
    assert (folder / "07_chart.png").is_file()
    assert not list(folder.glob("10_*"))


def test_host_run_when_approved_exports_after_final_text(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    _submit_until("awaiting_review", run_id, runs, tmp_path, capsys)
    assert main(["review", run_id, "--approve", "--runs-dir", str(runs)]) == 0
    assert _summary(capsys)["pending_step"] == "10_export"
    assert _submit(run_id, runs, tmp_path, capsys)["status"] == "completed"
    folder = iteration_dir(runs / run_id, 1)
    assert (folder / "10_report.xlsx").is_file()
    assert (folder / "10_briefing.pptx").is_file()


def test_host_run_when_tool_already_ran_does_not_repeat_it(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    quality = iteration_dir(runs / run_id, 1) / "01_quality.json"
    before = quality.stat().st_mtime_ns
    _submit(run_id, runs, tmp_path, capsys)
    assert quality.stat().st_mtime_ns == before


def test_host_run_when_data_too_short_requests_data_after_text(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys, periods=12)
    summary = _submit_until("waiting_for_data", run_id, runs, tmp_path, capsys)
    assert summary["status"] == "waiting_for_data"
    assert (iteration_dir(runs / run_id, 1) / "03_data_request.md").is_file()


def test_run_when_mapping_given_applies_it_to_handover_data(tmp_path, capsys):
    runs = tmp_path / "runs"
    short, full = tmp_path / "kurz.csv", tmp_path / "lang.csv"
    rows = [
        f"{year}-{month:02d}-01;{100 + year % 7 * month},5"
        for year in range(2019, 2025)
        for month in range(1, 13)
    ]
    short.write_text("Monat;Absatz\n" + "\n".join(rows[:12]) + "\n", encoding="utf-8")
    full.write_text("Monat;Absatz\n" + "\n".join(rows) + "\n", encoding="utf-8")
    options = ["--date-column", "Monat", "--value-column", "Absatz", "--no-llm", "--runs-dir", str(runs)]
    assert main(["run", "--data", str(short), *options]) == 0
    run_id = _summary(capsys)["run_id"]
    assert main(["handover", run_id, "--data", str(full), "--no-llm", "--runs-dir", str(runs)]) == 0
    assert _summary(capsys)["status"] == "awaiting_review"


def test_run_when_runs_dir_created_blocks_git_from_tracking_it(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    assert (runs / run_id / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_inspect_when_called_prints_json_structure(tmp_path, capsys):
    data = tmp_path / "reihe.csv"
    main(["synth", "--out", str(data)])
    capsys.readouterr()
    assert main(["inspect", str(data)]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 72


def test_render_agent_when_python_path_given_embeds_it_and_keeps_human_gate():
    text = render_agent(r"C:\tools\venv\Scripts\python.exe")
    assert text.startswith("---\n")
    assert r'& "C:\tools\venv\Scripts\python.exe" -m prognose' in text
    assert "{{PYTHON}}" not in text
    assert "--approve" in text
    assert "vscode/askQuestions" in text


def test_install_agent_when_targets_given_writes_each(tmp_path):
    first, second = tmp_path / "a" / "prognose.agent.md", tmp_path / "b" / "prognose.agent.md"
    assert install_agent("python", (first, second)) == (first, second)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_step_rejected_is_the_rejection_type_for_host_answers(tmp_path, capsys):
    run_id, runs = _start(tmp_path, capsys)
    with pytest.raises(StepRejected, match="98765"):
        submit_interpretation(
            runs / run_id,
            {"summary": "Wert 98765.", "notes": []},
            steps=load_steps(STEPS_DIR),
            interpreter=HostInterpreter(),
        )
