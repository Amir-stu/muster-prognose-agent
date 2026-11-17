import json

from prognose.cli import main


def _run_id(capsys) -> str:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{") :])["run_id"]


def test_cli_full_cycle_without_llm(tmp_path, capsys):
    data = tmp_path / "reihe.csv"
    runs = tmp_path / "runs"
    assert main(["synth", "--out", str(data)]) == 0
    assert data.is_file()
    capsys.readouterr()

    assert main(["run", "--data", str(data), "--horizon", "6", "--no-llm", "--runs-dir", str(runs)]) == 0
    run_id = _run_id(capsys)
    assert main(["status", run_id, "--runs-dir", str(runs)]) == 0
    assert '"awaiting_review"' in capsys.readouterr().out

    assert main(["review", run_id, "--approve", "--runs-dir", str(runs)]) == 0
    assert '"completed"' in capsys.readouterr().out


def test_cli_nein_branch_then_handover(tmp_path, capsys):
    short = tmp_path / "kurz.csv"
    full = tmp_path / "lang.csv"
    runs = tmp_path / "runs"
    main(["synth", "--out", str(short), "--periods", "12"])
    main(["synth", "--out", str(full)])
    capsys.readouterr()
    main(["run", "--data", str(short), "--no-llm", "--runs-dir", str(runs)])
    run_id = _run_id(capsys)
    assert main(["handover", run_id, "--data", str(full), "--runs-dir", str(runs)]) == 0
    assert '"awaiting_review"' in capsys.readouterr().out


def test_cli_when_step_fails_returns_error_code(tmp_path, capsys):
    data = tmp_path / "x.csv"
    data.write_text("datum,umsatz\n2024-01-01,1\n", encoding="utf-8")
    code = main(["run", "--data", str(data), "--no-llm", "--runs-dir", str(tmp_path / "runs")])
    assert code == 1
    assert "Spalte fehlt" in capsys.readouterr().err


def test_cli_review_adjust_passes_horizon(tmp_path, capsys):
    data = tmp_path / "reihe.csv"
    runs = tmp_path / "runs"
    main(["synth", "--out", str(data)])
    capsys.readouterr()
    main(["run", "--data", str(data), "--no-llm", "--runs-dir", str(runs)])
    run_id = _run_id(capsys)
    assert main(["review", run_id, "--adjust", "kürzer", "--horizon", "3", "--runs-dir", str(runs)]) == 0
    assert '"iteration": 2' in capsys.readouterr().out
