from pathlib import Path

import pytest

from prognose.config import load_config
from prognose.synthetic import SyntheticSpec, make_series

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return load_config(PROJECT_ROOT / "config.toml")


@pytest.fixture
def config_path():
    return PROJECT_ROOT / "config.toml"


@pytest.fixture
def steps_dir():
    return PROJECT_ROOT / "steps"


@pytest.fixture
def monthly_frame():
    return make_series(SyntheticSpec(periods=72, anomaly_positions=(30, 55)))
