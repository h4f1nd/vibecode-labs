"""Error-diffusion dithering.

Floyd-Steinberg uses Pillow's C implementation (fast and battle-tested).
Atkinson is not available in Pillow, so it runs in a tight Python loop limited
to the output width (384/576 dots) where the cost is acceptable.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

__all__ = ["atkinson", "floyd_steinberg"]


def floyd_steinberg(
    gray: NDArray[np.uint8],
    *,
    threshold: int = 128,
) -> NDArray[np.bool_]:
    """Floyd-Steinberg error diffusion via Pillow's C path.

    ``threshold`` is accepted for API symmetry but Pillow's implementation is
    fixed at the midpoint; use ``gamma``/``brightness`` to shift the result.
    """
    if gray.ndim != 2:
        raise ValueError(f"expected a 2-D grayscale array, got shape {gray.shape}")
    image = Image.fromarray(np.ascontiguousarray(gray, dtype=np.uint8), mode="L")
    mono = image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    ink: NDArray[np.bool_] = np.asarray(mono) == 0
    return ink


def atkinson(
    gray: NDArray[np.uint8],
    *,
    threshold: int = 128,
) -> NDArray[np.bool_]:
    """Atkinson error diffusion (6 neighbours, 1/8 of the error each).

    Atkinson throws away 1/4 of the error, which blows out highlights and
    crushes shadows - the high-contrast look of early 1-bit printers.
    """
    if gray.ndim != 2:
        raise ValueError(f"expected a 2-D grayscale array, got shape {gray.shape}")

    height, width = gray.shape
    if height == 0 or width == 0:
        return np.zeros((height, width), dtype=bool)

    # Pad by one column on the left and two on the right, plus two blank rows.
    # Every neighbour write is then in bounds, which removes ~6 bounds checks
    # per pixel.  Error that lands in the padding is simply discarded, exactly
    # as the explicit edge checks discarded it before.
    #
    # Plain Python lists, not numpy rows: indexing a numpy array yields a numpy
    # scalar and the arithmetic in the inner loop becomes ~3x slower.
    stride = width + 3
    blank = [0] * stride
    buf = [blank[:] for _ in range(height + 2)]
    for y in range(height):
        buf[y][1 : 1 + width] = gray[y].tolist()

    ink = bytearray(height * width)
    limit = int(threshold)

    for y in range(height):
        row = buf[y]
        below = buf[y + 1]
        below2 = buf[y + 2]
        base = y * width
        i = 1
        for x in range(width):
            old = row[i]
            if old > limit:
                error = old - 255
            else:
                error = old
                ink[base + x] = 1
            if error:
                share = error >> 3
                if share:
                    row[i + 1] += share
                    row[i + 2] += share
                    below[i - 1] += share
                    below[i] += share
                    below[i + 1] += share
                    below2[i] += share
            i += 1

    return np.frombuffer(bytes(ink), dtype=np.uint8).reshape(height, width).astype(bool)
