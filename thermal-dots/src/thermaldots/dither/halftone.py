"""Clustered-dot (newsprint) halftoning."""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

__all__ = ["clustered_dot", "halftone_dither"]


@lru_cache(maxsize=4)
def clustered_dot(size: int = 8) -> NDArray[np.float32]:
    """Rank cells of a square cell by distance from its centre.

    Growing a spot concentrically is what makes the classic newspaper rosette
    instead of the dispersed Bayer cross-hatch.
    """
    if size < 2:
        raise ValueError("size must be >= 2")
    centre = (size - 1) / 2.0
    cells = [(y, x) for y in range(size) for x in range(size)]

    def spot(cell: tuple[int, int]) -> tuple[float, float]:
        y, x = cell
        dy, dx = y - centre, x - centre
        # Euclidean spot function; the angle only breaks ties deterministically.
        return (math.hypot(dx, dy), math.atan2(dy, dx))

    ordered = sorted(cells, key=spot)
    matrix = np.empty((size, size), dtype=np.float32)
    for rank, (y, x) in enumerate(ordered):
        matrix[y, x] = (rank + 0.5) / (size * size)
    return matrix


def halftone_dither(
    gray: NDArray[np.uint8],
    *,
    size: int = 8,
) -> NDArray[np.bool_]:
    """Clustered-dot halftone of a grayscale image."""
    if gray.ndim != 2:
        raise ValueError(f"expected a 2-D grayscale array, got shape {gray.shape}")
    matrix = clustered_dot(size)
    height, width = gray.shape
    rows = np.arange(height) % size
    cols = np.arange(width) % size
    threshold = matrix[np.ix_(rows, cols)]
    return (gray.astype(np.float32) / 255.0) < threshold
