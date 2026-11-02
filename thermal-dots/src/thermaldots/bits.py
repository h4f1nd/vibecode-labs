"""1-bit packing helpers.

The canonical in-memory representation used across this package is a 2-D
``numpy`` boolean array called ``ink``: ``True`` means "the thermal head fires
here" (a black dot), ``False`` means paper.

Two different bit conventions exist in the wild and mixing them up is the
classic source of inverted thermal prints:

* ``ESC/POS`` raster (``GS v 0``): bit ``1`` = printed dot.
* ``Pillow`` mode ``"1"``: bit ``1`` = pixel value 255 = **white**.

:func:`pack_1bit` produces the ESC/POS convention.  :func:`ink_to_pil`
inverts on the way into Pillow so both stay truthful.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

__all__ = ["bytes_per_row", "ink_to_pil", "pack_1bit", "pil_to_ink", "unpack_1bit"]


def bytes_per_row(width_dots: int) -> int:
    """Number of bytes a single raster row occupies."""
    return (width_dots + 7) // 8


def pack_1bit(bits: NDArray[np.bool_] | NDArray[np.uint8]) -> bytes:
    """Pack a 2-D array MSB-first, padding each row to a byte boundary.

    This is byte-for-byte the payload format expected by ``GS v 0``.
    """
    arr = np.asarray(bits, dtype=np.uint8)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D array, got shape {arr.shape}")
    height, width = arr.shape
    if height == 0 or width == 0:
        return b""
    pad = (-width) % 8
    if pad:
        arr = np.pad(arr, ((0, 0), (0, pad)), mode="constant", constant_values=0)
    return np.packbits(arr, axis=1, bitorder="big").tobytes()


def unpack_1bit(data: bytes, width: int, height: int) -> NDArray[np.bool_]:
    """Inverse of :func:`pack_1bit` (row padding is discarded)."""
    row_bytes = bytes_per_row(width)
    expected = row_bytes * height
    if len(data) < expected:
        raise ValueError(f"expected at least {expected} bytes, got {len(data)}")
    raw = np.frombuffer(data[:expected], dtype=np.uint8)
    unpacked = np.unpackbits(raw, bitorder="big").reshape(height, row_bytes * 8)
    return unpacked[:, :width].astype(bool)


def ink_to_pil(ink: NDArray[np.bool_]) -> Image.Image:
    """Convert an ``ink`` bitmap to a Pillow ``"1"`` image.

    Round-tripping through ``fromarray`` + ``convert("1", dither=NONE)`` is
    exact for pure black/white input and avoids relying on Pillow's raw decoder
    behaviour for non-multiple-of-8 widths.
    """
    arr = np.asarray(ink, dtype=bool)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D array, got shape {arr.shape}")
    lum = np.where(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(lum, mode="L").convert("1", dither=Image.Dither.NONE)


def pil_to_ink(image: Image.Image) -> NDArray[np.bool_]:
    """Convert a Pillow image of any mode to an ``ink`` bitmap."""
    mono = image if image.mode == "1" else image.convert("1")
    ink: NDArray[np.bool_] = np.asarray(mono) == 0
    return ink
