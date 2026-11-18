from pathlib import Path

import pytest

from prognose import DEFAULT_CONFIG_PATH, STEPS_DIR
from prognose.config import load_config
from prognose.synthetic import SyntheticSpec, make_series


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG_PATH)


@pytest.fixture
def config_path() -> Path:
    return DEFAULT_CONFIG_PATH


@pytest.fixture
def steps_dir() -> Path:
    return STEPS_DIR


@pytest.fixture
def monthly_frame():
    return make_series(SyntheticSpec(periods=72, anomaly_positions=(30, 55)))
