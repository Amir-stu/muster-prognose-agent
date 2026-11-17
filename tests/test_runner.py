import json
import subprocess

import pytest

from prognose.runner import (
    AgentError,
    AgentSpec,
    UsageLimitError,
    build_command,
    parse_output,
    resolve_claude_executable,
    run_agent,
)

SPEC = AgentSpec(
    name="04_patterns", system_prompt="Du bist ...", model="sonnet", json_schema={"type": "object"}
)


def test_build_command_when_schema_given_passes_it_and_no_tools():
    command = build_command(SPEC, "claude.exe")
    assert command[:2] == ["claude.exe", "-p"]
    assert "--json-schema" in command
    assert command[command.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in command


def test_parse_output_when_success_returns_structured_and_cost():
    payload = {"result": "ok", "structured_output": {"summary": "x"}, "total_cost_usd": 0.12}
    result = parse_output(json.dumps(payload))
    assert result.structured == {"summary": "x"}
    assert result.cost_usd == 0.12


def test_parse_output_when_not_json_raises():
    with pytest.raises(AgentError, match="JSON"):
        parse_output("kein json")


def test_parse_output_when_error_result_raises():
    with pytest.raises(AgentError):
        parse_output(json.dumps({"is_error": True, "subtype": "error_max_budget", "result": "budget"}))


def test_parse_output_when_usage_limit_raises_specific_error():
    with pytest.raises(UsageLimitError):
        parse_output(json.dumps({"is_error": True, "result": "You've hit your usage limit"}))


def test_run_agent_when_process_succeeds_parses_stdout(monkeypatch, tmp_path):
    stdout = json.dumps({"result": "", "structured_output": {"summary": "s"}, "total_cost_usd": 0.01})

    def fake_run(command, **kwargs):
        assert kwargs["input"] == "Eingaben"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_agent(SPEC, "Eingaben", sandbox_dir=tmp_path / "s", timeout_s=5, claude_path="claude.exe")
    assert result.structured == {"summary": "s"}
    assert (tmp_path / "s").is_dir()


def test_run_agent_when_timeout_raises(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(AgentError, match="timed out"):
        run_agent(SPEC, "x", sandbox_dir=tmp_path, timeout_s=5, claude_path="claude.exe")


def test_run_agent_when_nonzero_exit_without_output_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr="boom"),
    )
    with pytest.raises(AgentError, match="boom"):
        run_agent(SPEC, "x", sandbox_dir=tmp_path, timeout_s=5, claude_path="claude.exe")


def test_resolve_executable_when_env_override_uses_it(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_PATH", "C:/tools/claude.exe")
    assert resolve_claude_executable() == "C:/tools/claude.exe"


def test_resolve_executable_when_not_on_path_raises(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(AgentError, match="not found"):
        resolve_claude_executable()


def test_resolve_executable_when_cmd_shim_without_native_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: str(tmp_path / "claude.cmd"))
    with pytest.raises(AgentError, match="shim"):
        resolve_claude_executable()


def test_resolve_executable_when_plain_binary_returns_it(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    assert resolve_claude_executable() == "/usr/bin/claude"
