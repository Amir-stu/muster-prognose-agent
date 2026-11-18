"""Muster- und Prognose-Agent: deterministic forecasting tools orchestrated with LLM interpretation steps."""

from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
DEFAULT_CONFIG_PATH = RESOURCES_DIR / "config.toml"
STEPS_DIR = RESOURCES_DIR / "steps"
AGENT_TEMPLATE_PATH = RESOURCES_DIR / "copilot" / "prognose.agent.md"
DEFAULT_RUNS_DIR_NAME = "prognose-runs"
