"""Run one step subagent as a headless `claude -p` subprocess, authenticated by the user's Claude Code login.

Ported from deep-research-cli: it calls the native claude.exe, never the cmd.exe shim, which mangles
multi-line arguments on Windows.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AgentError(RuntimeError):
    """An agent run failed: CLI missing, non-zero exit, timeout, or an error result."""


class UsageLimitError(AgentError):
    """The Claude subscription usage limit was hit; further calls fail until it resets."""


USAGE_LIMIT_PATTERN = re.compile(r"hit your .*limit|usage limit", re.IGNORECASE)
SHELL_SHIM_SUFFIXES = (".cmd", ".bat")
NPM_NATIVE_BINARY = Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
MESSAGE_LIMIT = 300


@dataclass(frozen=True)
class AgentSpec:
    name: str
    system_prompt: str
    model: str
    json_schema: dict[str, Any] | None = None
    max_budget_usd: float = 0.30


@dataclass(frozen=True)
class AgentResult:
    text: str
    structured: dict[str, Any] | None
    cost_usd: float


def build_command(spec: AgentSpec, claude_path: str) -> list[str]:
    command = [
        claude_path,
        "-p",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--setting-sources",
        "",
        # Without these the user's MCP connectors and skill list load into every subagent.
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--model",
        spec.model,
        "--system-prompt",
        spec.system_prompt,
        "--max-budget-usd",
        str(spec.max_budget_usd),
        "--tools",
        "",
    ]
    if spec.json_schema is None:
        return command
    return [*command, "--json-schema", json.dumps(spec.json_schema, separators=(",", ":"))]


def parse_output(stdout: str) -> AgentResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise AgentError(f"claude output is not valid JSON: {stdout[:MESSAGE_LIMIT]!r}") from error
    if payload.get("is_error"):
        message = str(payload.get("result"))
        if USAGE_LIMIT_PATTERN.search(message):
            raise UsageLimitError(message[:MESSAGE_LIMIT])
        raise AgentError(f"agent ended with {payload.get('subtype')}: {message[:MESSAGE_LIMIT]}")
    return AgentResult(
        text=payload.get("result") or "",
        structured=payload.get("structured_output"),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
    )


def resolve_claude_executable() -> str:
    override = os.environ.get("CLAUDE_CLI_PATH")
    if override:
        return override
    found = shutil.which("claude")
    if found is None:
        raise AgentError("claude CLI not found on PATH - install Claude Code and run `claude auth login`")
    if not found.lower().endswith(SHELL_SHIM_SUFFIXES):
        return found
    native = Path(found).parent / NPM_NATIVE_BINARY
    if native.is_file():
        return str(native)
    raise AgentError(f"{found} is a cmd.exe shim and the native binary was not found; set CLAUDE_CLI_PATH")


def run_agent(
    spec: AgentSpec, prompt: str, *, sandbox_dir: Path, timeout_s: int, claude_path: str | None = None
) -> AgentResult:
    executable = claude_path or resolve_claude_executable()
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            build_command(spec, executable),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=sandbox_dir,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AgentError(f"{spec.name} timed out after {timeout_s}s") from error
    if completed.returncode != 0 and not completed.stdout.strip():
        raise AgentError(
            f"{spec.name} exited {completed.returncode}: {completed.stderr.strip()[:MESSAGE_LIMIT]}"
        )
    return parse_output(completed.stdout)
