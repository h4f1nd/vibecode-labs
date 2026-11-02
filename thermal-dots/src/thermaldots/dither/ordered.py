"""Ordered (Bayer) dithering - the crisp "dot matrix" look.

The threshold maps are the classic recursive Bayer matrices:

    M(2n) = 1/(2n)^2 * [[4M(n),      4M(n) + 2J],
                        [4M(n) + 3J, 4M(n) +   J]]

with ``M(1) = [[0]]``.  See https://en.wikipedia.org/wiki/Ordered_dithering
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

__all__ = ["bayer_matrix", "ordered_dither"]


@lru_cache(maxsize=8)
def bayer_matrix(size: int) -> NDArray[np.float32]:
    """Return a normalised ``size x size`` Bayer threshold map in ``[0, 1)``."""
    if size < 2 or size & (size - 1):
        raise ValueError(f"Bayer size must be a power of two >= 2, got {size}")

    matrix = np.zeros((1, 1), dtype=np.uint32)
    while matrix.shape[0] < size:
        matrix = np.block(
            [
                [4 * matrix, 4 * matrix + 2],
                [4 * matrix + 3, 4 * matrix + 1],
            ]
        )
    # +0.5 keeps every threshold strictly inside (0, 1) so pure black stays
    # fully inked and pure white stays fully blank.
    return ((matrix + 0.5) / matrix.size).astype(np.float32)


def _threshold_pattern(size: int, height: int, width: int) -> NDArray[np.float32]:
    matrix = bayer_matrix(size)
    rows = np.arange(height) % size
    cols = np.arange(width) % size
    return matrix[np.ix_(rows, cols)]


def ordered_dither(
    gray: NDArray[np.uint8],
    *,
    size: int = 4,
    amount: float = 1.0,
) -> NDArray[np.bool_]:
    """Threshold the image against a tiled Bayer map.

    ``amount`` in ``[0, 1]`` shrinks the pattern towards a flat 50 % threshold,
    which is useful when the cross-hatch is too aggressive on a photo.
    """
    if gray.ndim != 2:
        raise ValueError(f"expected a 2-D grayscale array, got shape {gray.shape}")
    if not 0.0 <= amount <= 1.0:
        raise ValueError("amount must be between 0 and 1")

    height, width = gray.shape
    pattern = _threshold_pattern(size, height, width)
    if amount < 1.0:
        pattern = 0.5 + (pattern - 0.5) * amount

    # Normalised compare: ink where the pixel is darker than its cell threshold.
    return (gray.astype(np.float32) / 255.0) < pattern
