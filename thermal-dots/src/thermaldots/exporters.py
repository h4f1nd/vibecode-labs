"""Exporters: turn an ``ink`` bitmap into bytes somebody else can consume.

All functions here are pure and take ``ink`` (2-D bool array, True = printed
dot).  They deliberately know nothing about :mod:`thermaldots.models` so the
dependency graph stays acyclic.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .bits import ink_to_pil, pack_1bit
from .errors import OutputError, OutputInUseError

__all__ = [
    "atomic_write",
    "bmp_bytes",
    "escpos_bytes",
    "half_block_text",
    "png_bytes",
    "upscale_ink",
    "write_sidecar",
]

_ESC = 0x1B
_GS = 0x1D


def _as_ink(ink: NDArray[np.bool_]) -> NDArray[np.bool_]:
    arr = np.asarray(ink, dtype=bool)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D ink array, got shape {arr.shape}")
    if arr.size == 0:
        raise ValueError("ink bitmap is empty")
    return arr


def upscale_ink(ink: NDArray[np.bool_], factor: int) -> NDArray[np.bool_]:
    """Repeat every dot ``factor`` times, nearest-neighbour.

    This changes how big the raster file is, never what the dots say: the
    result is exactly the same pattern, with each 1-bit pixel drawn as a
    ``factor x factor`` block.  It is deliberately not a smooth resize - any
    interpolation would invent grey pixels that a 1-bit file cannot store.
    """
    arr = _as_ink(ink)
    if factor < 1:
        raise ValueError(f"upscale factor must be at least 1, got {factor}")
    if factor == 1:
        return arr
    return np.repeat(np.repeat(arr, factor, axis=0), factor, axis=1)


def png_bytes(
    ink: NDArray[np.bool_], *, compress_level: int = 6, upscale: int = 1
) -> bytes:
    """1-bit PNG, exact dot dimensions (or ``upscale`` times larger)."""
    image = ink_to_pil(upscale_ink(ink, upscale))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=compress_level)
    return buffer.getvalue()


def bmp_bytes(ink: NDArray[np.bool_], *, upscale: int = 1) -> bytes:
    """1-bit BMP, exact dot dimensions (or ``upscale`` times larger)."""
    image = ink_to_pil(upscale_ink(ink, upscale))
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    return buffer.getvalue()


def escpos_bytes(
    ink: NDArray[np.bool_],
    *,
    init: bool = True,
    feed_lines: int = 3,
    cut: bool = False,
    fragment_rows: int = 960,
) -> bytes:
    """Frame the bitmap as ``GS v 0`` raster blocks.

    ``fragment_rows`` splits tall images into several blocks: cheap clone
    firmware overruns its buffer above ~1000 rows per command.
    """
    arr = _as_ink(ink)
    height, width = arr.shape
    if fragment_rows < 1:
        raise ValueError("fragment_rows must be >= 1")
    row_bytes = (width + 7) // 8

    out = bytearray()
    if init:
        out += bytes((_ESC, 0x40))  # ESC @  (initialise)
    for start in range(0, height, fragment_rows):
        band = arr[start : start + fragment_rows]
        band_height = band.shape[0]
        out += bytes((_GS, 0x76, 0x30, 0x00))  # GS v 0 0 (normal density)
        out += row_bytes.to_bytes(2, "little")
        out += band_height.to_bytes(2, "little")
        out += pack_1bit(band)
    if feed_lines:
        out += bytes((_ESC, 0x64, min(255, max(0, feed_lines))))  # ESC d n
    if cut:
        out += bytes((_GS, 0x56, 0x00))  # GS V 0 (full cut)
    return bytes(out)


def half_block_text(ink: NDArray[np.bool_], *, max_width: int = 48) -> str:
    """Render the bitmap as Unicode half blocks for a terminal preview.

    Each character covers two vertical dots, so a 384x600 bitmap becomes a
    48x150 grid at ``max_width=48``.  Ink is drawn with bright blocks so it
    reads correctly on a dark terminal.
    """
    arr = _as_ink(ink)
    width = arr.shape[1]
    if max_width < 1:
        raise ValueError("max_width must be >= 1")
    step = max(1, (width + max_width - 1) // max_width)
    small = arr[::step, ::step]
    if small.shape[0] % 2:
        small = np.vstack([small, np.zeros((1, small.shape[1]), dtype=bool)])

    top = small[0::2]
    bottom = small[1::2]
    lines: list[str] = []
    for upper, lower in zip(top, bottom, strict=True):
        row = "".join(
            "\u2588" if a and b else "\u2580" if a else "\u2584" if b else " "
            for a, b in zip(upper, lower, strict=True)
        )
        lines.append(row.rstrip())
    return "\n".join(lines)


def atomic_write(path: str | os.PathLike[str], data: bytes) -> Path:
    """Write ``data`` to ``path`` atomically (temp file in the same directory).

    A locked destination (file open in a viewer, or held by the print app) is
    reported as :class:`OutputInUseError` rather than a bare ``PermissionError``
    - it is by far the most common write failure on Windows and it is the only
    one the user can fix.
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OutputError(f"Cannot create {target.parent}: {error}") from error

    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.stem}-", suffix=target.suffix + ".tmp", dir=str(target.parent)
        )
    except OSError as error:
        raise OutputError(f"Cannot write to {target.parent}: {error}") from error

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except PermissionError as error:
        tmp_path.unlink(missing_ok=True)
        raise OutputInUseError(
            f"Cannot overwrite {target} - the file is open in another application."
        ) from error
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise OutputError(f"Cannot write {target}: {error}") from error
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def write_sidecar(path: str | os.PathLike[str], metadata: dict[str, Any]) -> Path:
    """Write ``<file>.json`` next to an export for traceability."""
    target = Path(path).with_suffix(Path(path).suffix + ".json")
    payload = json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")
    return atomic_write(target, payload)


def describe_blocks(images: Iterable[Image.Image]) -> list[tuple[int, int]]:
    """Tiny helper used by tests to assert dimensions of a sequence."""
    return [image.size for image in images]
