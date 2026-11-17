"""Muster- und Prognose-Agent: deterministic forecasting tools orchestrated with LLM interpretation steps."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
STEPS_DIR = PROJECT_ROOT / "steps"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "runs"
