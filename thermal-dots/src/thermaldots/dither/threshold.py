"""Global threshold strategies."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

__all__ = ["fixed_threshold", "mean_threshold", "otsu_threshold"]


def otsu_threshold(gray: NDArray[np.uint8]) -> int:
    """Otsu's method on a 256-bin histogram (vectorised, ~0.2 ms)."""
    if gray.size == 0:
        return 128
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128

    weights = np.cumsum(hist)
    means = np.cumsum(hist * np.arange(256))
    weight_bg = weights
    weight_fg = total - weight_bg
    mean_bg = np.divide(means, weight_bg, out=np.zeros(256), where=weight_bg > 0)
    total_mean = means[-1] / total
    mean_fg = np.divide(
        total_mean * total - means,
        weight_fg,
        out=np.zeros(256),
        where=weight_fg > 0,
    )
    variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    variance[weight_bg <= 0] = 0
    variance[weight_fg <= 0] = 0
    best = float(variance.max())
    if best <= 0:
        return 128
    # Otsu is flat across a plateau when the histogram has two separate peaks;
    # the middle of that plateau is the least surprising threshold.
    plateau = np.flatnonzero(variance >= best - 1e-9)
    return int(np.median(plateau))


def fixed_threshold(gray: NDArray[np.uint8], threshold: int = 128) -> NDArray[np.bool_]:
    return np.asarray(gray < threshold, dtype=bool)


def mean_threshold(
    gray: NDArray[np.uint8],
    threshold: int | None = None,
) -> NDArray[np.bool_]:
    """Threshold at ``threshold``, or at Otsu's optimum when omitted.

    A fixed global threshold loses information on uneven lighting; Otsu is a
    better default for line art and logos while staying predictable.
    """
    limit = otsu_threshold(gray) if threshold is None else int(threshold)
    return fixed_threshold(gray, limit)
