"""Install the GitHub Copilot agent file, bound to the Python environment this package runs in."""

import os
from collections.abc import Iterable
from pathlib import Path

from prognose import AGENT_TEMPLATE_PATH

AGENT_FILE_NAME = "prognose.agent.md"
PYTHON_PLACEHOLDER = "{{PYTHON}}"
VSCODE_EDITIONS = ("Code", "Code - Insiders")


def render_agent(python_path: str) -> str:
    return AGENT_TEMPLATE_PATH.read_text(encoding="utf-8").replace(PYTHON_PLACEHOLDER, python_path)


def _vscode_user_dirs() -> list[Path]:
    appdata = os.environ.get("APPDATA")
    roots = [Path(appdata)] if appdata else [Path.home() / ".config"]
    return [root / edition / "User" for root in roots for edition in VSCODE_EDITIONS]


def default_targets() -> tuple[Path, ...]:
    """The Copilot user folder, plus the prompts folder of every installed VS Code edition."""
    editor_targets = [
        folder / "prompts" / AGENT_FILE_NAME for folder in _vscode_user_dirs() if folder.is_dir()
    ]
    return (Path.home() / ".copilot" / "agents" / AGENT_FILE_NAME, *editor_targets)


def install_agent(python_path: str, targets: Iterable[Path]) -> tuple[Path, ...]:
    text = render_agent(python_path)
    written = tuple(targets)
    for target in written:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return written
