"""Golden fingerprints per dither mode and paper size.

These are characterisation tests: they do not say the output is *good*, only
that it did not change.  Any diff here changes every user's prints, so it must
be an intentional change followed by ``tests/golden/regen.py``.
"""

from __future__ import annotations

import json

import pytest

from tests.golden.regen import HASHES, build


@pytest.fixture(scope="module")
def expected() -> dict[str, str]:
    assert HASHES.exists(), "run: .venv\\Scripts\\python tests\\golden\\regen.py"
    return json.loads(HASHES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actual() -> dict[str, str]:
    return build()


def test_fingerprint_file_covers_every_case(actual: dict[str, str], expected: dict[str, str]) -> None:
    assert set(actual) == set(expected)


def test_fingerprints_match(
    actual: dict[str, str], expected: dict[str, str]
) -> None:
    changed = {
        name: (expected.get(name), actual.get(name))
        for name in sorted(expected)
        if expected.get(name) != actual.get(name)
    }
    assert not changed, (
        "dither output changed (expected -> actual): "
        f"{changed}. If that is intended, re-run tests/golden/regen.py."
    )


def test_conversion_is_deterministic() -> None:
    assert build() == build()
