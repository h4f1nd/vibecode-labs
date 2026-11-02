from __future__ import annotations

import os
from pathlib import Path

import pytest

from datbuilder import write_sample


@pytest.fixture
def sample_dat(tmp_path: Path) -> Path:
    return write_sample(tmp_path / "SAMPLE.DAT")


@pytest.fixture
def reference_dir() -> Path:
    raw = os.environ.get("DOTDAT_REFERENCE", "reference")
    path = Path(raw)
    if not path.is_dir():
        pytest.skip("reference tables not found; set DOTDAT_REFERENCE")
    return path
