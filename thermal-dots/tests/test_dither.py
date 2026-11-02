from __future__ import annotations

import numpy as np
import pytest

from thermaldots.dither import (
    atkinson,
    bayer_matrix,
    clustered_dot,
    floyd_steinberg,
    halftone_dither,
    mean_threshold,
    ordered_dither,
    otsu_threshold,
)


def flat(value: int, size: int = 64) -> np.ndarray:
    return np.full((size, size), value, dtype=np.uint8)


def ramp(size: int = 64) -> np.ndarray:
    values = np.linspace(0, 255, size, dtype=np.float32)
    return np.tile(values, (size, 1)).astype(np.uint8)


def test_bayer_matrix_recursion() -> None:
    m2 = np.floor(bayer_matrix(2) * 4).astype(int)
    assert np.array_equal(m2, np.array([[0, 2], [3, 1]]))
    m4 = np.floor(bayer_matrix(4) * 16).astype(int)
    assert np.array_equal(m4[0], [0, 8, 2, 10])
    assert np.array_equal(m4[1], [12, 4, 14, 6])


def test_bayer_requires_power_of_two() -> None:
    with pytest.raises(ValueError):
        bayer_matrix(6)


def test_ordered_extremes() -> None:
    assert ordered_dither(flat(0), size=4).all()
    assert not ordered_dither(flat(255), size=4).any()


def test_ordered_is_deterministic() -> None:
    gray = ramp()
    assert np.array_equal(ordered_dither(gray, size=4), ordered_dither(gray, size=4))


@pytest.mark.parametrize("size", [4, 8])
def test_ordered_midpoint_ratio(size: int) -> None:
    ratio = ordered_dither(flat(128), size=size).mean()
    assert 0.35 < ratio < 0.65


def test_ordered_darker_means_more_ink() -> None:
    assert ordered_dither(flat(64)).mean() > ordered_dither(flat(192)).mean()


def test_halftone_shape_and_extremes() -> None:
    assert halftone_dither(flat(0)).all()
    assert not halftone_dither(flat(255)).any()
    assert halftone_dither(ramp()).shape == (64, 64)


def test_clustered_matrix_is_a_permutation() -> None:
    matrix = clustered_dot(8)
    assert matrix.shape == (8, 8)
    assert len(np.unique(matrix)) == 64


def test_otsu_separates_bimodal() -> None:
    gray = np.concatenate([flat(30, 32).ravel(), flat(220, 32).ravel()])
    threshold = otsu_threshold(gray)
    assert 30 < threshold < 220


def test_mean_threshold_auto_and_explicit() -> None:
    gray = ramp()
    auto = mean_threshold(gray)
    explicit = mean_threshold(gray, 60)
    assert explicit.sum() < auto.sum()


def test_floyd_steinberg_dtype_and_extremes() -> None:
    assert floyd_steinberg(flat(0)).all()
    assert not floyd_steinberg(flat(255)).any()
    assert floyd_steinberg(ramp()).dtype == bool


def test_atkinson_midpoint_ratio() -> None:
    ratio = atkinson(flat(128), threshold=128).mean()
    assert 0.3 < ratio < 0.7


def test_atkinson_deterministic_and_shaped() -> None:
    gray = ramp()
    first = atkinson(gray)
    second = atkinson(gray)
    assert first.shape == gray.shape
    assert np.array_equal(first, second)


def test_atkinson_beats_threshold_on_gradient() -> None:
    gray = ramp(128)
    diffused = atkinson(gray)
    # The first column is pure black, the last is pure white.
    assert diffused[:, 0].all()
    assert not diffused[:, -1].any()


def test_dither_rejects_non_2d() -> None:
    with pytest.raises(ValueError):
        ordered_dither(np.zeros((2, 2, 2), dtype=np.uint8))
