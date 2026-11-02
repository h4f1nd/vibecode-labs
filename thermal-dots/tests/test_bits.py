from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from thermaldots.bits import bytes_per_row, ink_to_pil, pack_1bit, unpack_1bit


def test_bytes_per_row_rounds_up() -> None:
    assert bytes_per_row(384) == 48
    assert bytes_per_row(576) == 72
    assert bytes_per_row(1) == 1
    assert bytes_per_row(9) == 2


def test_pack_is_msb_first() -> None:
    row = np.array([[1, 0, 1, 0, 1, 0, 1, 0]], dtype=bool)
    assert pack_1bit(row) == b"\xaa"
    assert pack_1bit(~row) == b"\x55"


def test_pack_pads_partial_rows() -> None:
    row = np.ones((1, 9), dtype=bool)
    assert pack_1bit(row) == b"\xff\x80"


def test_pack_rejects_non_2d() -> None:
    with pytest.raises(ValueError):
        pack_1bit(np.zeros(4, dtype=bool))


@given(
    width=st.integers(min_value=1, max_value=300),
    height=st.integers(min_value=1, max_value=40),
    seed=st.integers(min_value=0, max_value=2**16),
)
def test_pack_length_invariant(width: int, height: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=(height, width)).astype(bool)
    data = pack_1bit(bits)
    assert len(data) == bytes_per_row(width) * height

    restored = unpack_1bit(data, width, height)
    assert restored.shape == (height, width)
    assert np.array_equal(restored, bits)


def test_ink_to_pil_roundtrip() -> None:
    ink = np.array(
        [
            [1, 1, 0, 0, 1, 0, 1, 1],
            [0, 0, 1, 1, 0, 1, 0, 0],
        ],
        dtype=bool,
    )
    image = ink_to_pil(ink)
    assert image.mode == "1"
    assert image.size == (8, 2)
    assert np.array_equal(np.asarray(image) == 0, ink)


def test_ink_to_pil_odd_width() -> None:
    ink = np.array([[1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0]], dtype=bool)
    image = ink_to_pil(ink)
    assert image.size == (11, 1)
    assert np.array_equal(np.asarray(image) == 0, ink)
