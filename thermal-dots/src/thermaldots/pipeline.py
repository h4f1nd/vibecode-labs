"""Image -> dots pipeline.

``convert()`` is a pure function of (source, options): same input, same dots,
always.  Nothing here touches the network, the printer, or global state except
a small bounded cache of decoded images.
"""

from __future__ import annotations

import contextlib
import io
import threading
import time
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from . import dither as dithering
from .errors import (
    ConversionCancelled,
    ImageTooLargeError,
    InvalidOptionsError,
    SourceNotFoundError,
    ThermalDotsError,
    UnsupportedImageError,
)
from .models import (
    ConversionResult,
    ConvertOptions,
    DitherMode,
    ProgressFn,
    ScaleMode,
    StageEvent,
)

__all__ = [
    "STAGES",
    "CancellationToken",
    "clear_cache",
    "convert",
    "convert_bytes",
    "probe",
]

STAGES = ("decode", "fit", "tone", "dither", "done")

Source = str | Path | bytes | bytearray | BinaryIO | Image.Image | NDArray[np.uint8]


class CancellationToken:
    """Cooperative cancellation checked between stages."""

    __slots__ = ("_cancelled",)

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def check(self) -> None:
        if self._cancelled:
            raise ConversionCancelled()


# --------------------------------------------------------------------------- #
# Decoded-image cache (changing dither/gamma must not re-decode the file)
# --------------------------------------------------------------------------- #

_CACHE_LIMIT = 4
_cache: OrderedDict[tuple[Any, ...], Image.Image] = OrderedDict()
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_key(path: Path, options: ConvertOptions) -> tuple[Any, ...]:
    stat = path.stat()
    return (
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        *_geometry_key(options),
    )


def _geometry_key(options: ConvertOptions) -> tuple[Any, ...]:
    """Everything that changes the *prepared* pixels (not the dither pattern)."""
    return (
        options.resolved_width(),
        options.scale.value,
        options.rotate,
        options.margin,
        options.border,
        options.max_height_dots,
        options.max_source_pixels,
    )


def _memory_key(token: str, options: ConvertOptions) -> tuple[Any, ...]:
    return ("mem", token, *_geometry_key(options))


def _cache_get(key: tuple[Any, ...]) -> Image.Image | None:
    with _cache_lock:
        image = _cache.get(key)
        if image is not None:
            _cache.move_to_end(key)
        return image


def _cache_put(key: tuple[Any, ...], image: Image.Image) -> None:
    with _cache_lock:
        _cache[key] = image
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)


# --------------------------------------------------------------------------- #
# Source handling
# --------------------------------------------------------------------------- #


def _open_source(source: Source) -> tuple[Image.Image, str]:
    if isinstance(source, Image.Image):
        return source.copy(), "<image>"
    if isinstance(source, np.ndarray):
        return _from_array(source), "<array>"
    if isinstance(source, (bytes, bytearray)):
        return _open_stream(io.BytesIO(bytes(source)), "<bytes>")
    if hasattr(source, "read"):
        data = source.read()
        name = str(getattr(source, "name", "<stream>"))
        return _open_stream(io.BytesIO(data), name)

    path = Path(source)
    if not path.exists():
        raise SourceNotFoundError(
            f"File not found: {path}", hint="Check the path, or drag the file into the app."
        )
    if path.is_dir():
        raise SourceNotFoundError(
            f"{path} is a folder, not an image.", hint="Point at a single image file."
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(path)  # header only: pixels load after draft()
        except Image.DecompressionBombError as error:  # pragma: no cover - huge input
            raise ImageTooLargeError(str(error)) from error
        except Image.DecompressionBombWarning as error:
            raise ImageTooLargeError(str(error)) from error
        except UnidentifiedImageError as error:
            raise UnsupportedImageError(f"Cannot read {path.name!r}.") from error
        except OSError as error:
            raise UnsupportedImageError(
                f"Cannot read {path.name!r}: {error}",
                hint="The file may be truncated or use an unsupported codec.",
            ) from error
    return image, path.name


def _open_stream(stream: io.BytesIO, name: str) -> tuple[Image.Image, str]:
    try:
        image = Image.open(stream)  # header only, see _open_source
    except UnidentifiedImageError as error:
        raise UnsupportedImageError(f"Cannot read {name!r}.") from error
    except OSError as error:
        raise UnsupportedImageError(f"Cannot read {name!r}: {error}") from error
    return image, name


def _load_pixels(image: Image.Image, name: str) -> None:
    """Force decoding now that :func:`_draft` had a chance to shrink the work."""
    try:
        image.load()
    except OSError as error:
        raise UnsupportedImageError(
            f"Cannot decode {name!r}: {error}",
            hint="The file may be truncated or use an unsupported codec.",
        ) from error


def _from_array(array: NDArray[np.uint8]) -> Image.Image:
    data = np.asarray(array)
    if data.ndim not in (2, 3):
        raise UnsupportedImageError(f"Expected a 2-D or 3-D array, got shape {data.shape}.")
    if np.issubdtype(data.dtype, np.floating):
        peak = 1.0 if float(np.max(data, initial=0.0)) <= 1.0 else 255.0
        data = np.clip(data / peak * 255.0, 0, 255)
    data = data.astype(np.uint8, copy=False)
    if data.ndim == 2:
        mode = "L"
    elif data.shape[2] == 3:
        mode = "RGB"
    elif data.shape[2] == 4:
        mode = "RGBA"
    else:
        raise UnsupportedImageError(f"Unsupported channel count: {data.shape[2]}.")
    return Image.fromarray(np.ascontiguousarray(data), mode=mode)


def _guard_size(image: Image.Image, options: ConvertOptions) -> None:
    pixels = image.size[0] * image.size[1]
    if pixels > options.max_source_pixels:
        raise ImageTooLargeError(
            f"{image.size[0]}x{image.size[1]} px ({pixels:,} pixels) exceeds the "
            f"{options.max_source_pixels:,} pixel safety limit."
        )


# --------------------------------------------------------------------------- #
# Geometry / colour preparation
# --------------------------------------------------------------------------- #


def _draft(image: Image.Image, target_width: int) -> Image.Image:
    """Ask the JPEG decoder for a downscaled image before paying for full decode."""
    if image.format not in ("JPEG", "MPO") or target_width < 1:
        return image
    if image.size[0] <= target_width:
        return image
    ratio = target_width / image.size[0]
    hint = (max(1, int(image.size[0] * ratio)), max(1, int(image.size[1] * ratio)))
    try:
        image.draft("L", hint)
    except Exception:  # pragma: no cover - decoder specific
        return image
    return image


def _to_gray(image: Image.Image) -> Image.Image:
    """Flatten transparency onto white, then produce an 8-bit luma image."""
    if image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)

    if image.mode.startswith("I;16") or image.mode in ("I", "F"):
        data = np.asarray(image).astype(np.float64)
        peak = 65535.0 if image.mode.startswith("I;16") else float(np.max(data, initial=0.0))
        peak = max(1.0, peak)
        data = np.clip(data * (255.0 / peak), 0, 255).astype(np.uint8)
        return Image.fromarray(data, mode="L")

    if image.mode == "CMYK":
        image = image.convert("RGB")
    return image.convert("L")


def _fit(image: Image.Image, options: ConvertOptions) -> Image.Image:
    """Resize/crop to the printable width, then centre on a paper-width canvas."""
    width, height = image.size
    box_w = options.inner_width
    implied_h = max(1, round(height * box_w / width)) if width else 1
    box_h = max(1, options.max_height_dots or implied_h)

    if options.scale is ScaleMode.FILL:
        # ImageOps.fit always returns exactly box_w x box_h. Doing the crop by
        # hand can leave a one-dot gap when the scaled size rounds down, and
        # crop() fills anything outside the image with black - which prints.
        resized = ImageOps.fit(image, (box_w, box_h), method=Image.Resampling.LANCZOS)
    elif options.scale is ScaleMode.STRETCH:
        resized = image.resize((box_w, box_h), Image.Resampling.LANCZOS)
    else:
        factor = min(box_w / width, box_h / height)
        resized = image.resize(
            (max(1, round(width * factor)), max(1, round(height * factor))),
            Image.Resampling.LANCZOS,
        )

    frame = 1 if options.border else 0
    canvas_w = options.resolved_width()
    canvas_h = resized.height + 2 * options.margin + 2 * frame
    canvas = Image.new("L", (canvas_w, canvas_h), 255)

    paste_x = (canvas_w - resized.width) // 2
    paste_y = options.margin + frame
    canvas.paste(resized, (paste_x, paste_y))

    if frame:
        draw = ImageDraw.Draw(canvas)
        draw.rectangle(
            (paste_x - 1, paste_y - 1, paste_x + resized.width, paste_y + resized.height),
            outline=0,
        )
    return canvas


def _prepare(image: Image.Image, options: ConvertOptions) -> Image.Image:
    with contextlib.suppress(Exception):  # malformed EXIF must not kill the job
        image = ImageOps.exif_transpose(image)
    if options.rotate:
        image = image.rotate(-options.rotate, expand=True)
    gray = _to_gray(image)
    return _fit(gray, options)


def _tone(image: Image.Image, options: ConvertOptions) -> Image.Image:
    if (
        options.gamma == 1.0
        and options.brightness == 0
        and options.contrast == 1.0
        and not options.invert
    ):
        return image

    ramp = np.arange(256, dtype=np.float32) / 255.0
    ramp = np.power(ramp, options.gamma)
    ramp = (ramp - 0.5) * options.contrast + 0.5
    ramp = ramp * 255.0 + options.brightness
    if options.invert:
        ramp = 255.0 - ramp
    lut = np.clip(ramp, 0, 255).astype(np.uint8)
    return image.point(lut.tobytes())


def _dither(image: Image.Image, options: ConvertOptions) -> NDArray[np.bool_]:
    gray = np.asarray(image, dtype=np.uint8)
    mode = options.dither

    if mode is DitherMode.BAYER4:
        return dithering.ordered_dither(gray, size=4)
    if mode is DitherMode.BAYER8:
        return dithering.ordered_dither(gray, size=8)
    if mode is DitherMode.HALFTONE:
        return dithering.halftone_dither(gray, size=8)
    if mode is DitherMode.ATKINSON:
        return dithering.atkinson(gray, threshold=options.threshold)
    if mode is DitherMode.FLOYD_STEINBERG:
        return dithering.floyd_steinberg(gray)
    if mode is DitherMode.MEAN:
        auto = None if options.auto_threshold else options.threshold
        return dithering.mean_threshold(gray, auto)
    if mode is DitherMode.NONE:
        return dithering.mean_threshold(gray, options.threshold)

    raise InvalidOptionsError(f"Unhandled dither mode {mode!r}.")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _emit(progress: ProgressFn | None, index: int, stage: str, message: str) -> None:
    if progress is None:
        return
    progress(StageEvent(stage=stage, index=index, total=len(STAGES), message=message))


def convert(
    source: Source,
    options: ConvertOptions | None = None,
    *,
    progress: ProgressFn | None = None,
    cancel: CancellationToken | None = None,
    cache_key: str | None = None,
) -> ConversionResult:
    """Convert one image to a 1-bit ``ink`` bitmap.

    ``cache_key`` lets in-memory callers (the GUI) reuse the *decoded and
    fitted* image across previews.  Without it, dragging a slider on a 24 MP
    photo would pay for a full JPEG decode on every tick; the token only needs
    to be unique per image, its name or a UUID is fine.
    """
    opts = options or ConvertOptions()
    token = cancel or CancellationToken()
    timings: dict[str, float] = {}
    started = time.perf_counter()

    _emit(progress, 1, "decode", "reading source")
    token.check()

    key: tuple[Any, ...] | None = None
    prepared: Image.Image | None = None
    label = "<memory>"

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            # Let _open_source raise the precise error.
            _open_source(source)
        key = _cache_key(path, opts)
        prepared = _cache_get(key)
        label = path.name
    elif cache_key is not None:
        key = _memory_key(cache_key, opts)
        prepared = _cache_get(key)

    if prepared is None:
        image, label = _open_source(source)
        _guard_size(image, opts)
        image = _draft(image, opts.inner_width)
        _load_pixels(image, label)
        prepared = _prepare(image, opts)
        if key is not None:
            _cache_put(key, prepared)

    now = time.perf_counter()
    timings["decode"] = (now - started) * 1000

    _emit(progress, 2, "fit", f"fitted to {prepared.width} dots")
    token.check()

    toned = _tone(prepared, opts)
    now = time.perf_counter()
    timings["tone"] = (now - started) * 1000 - timings["decode"]

    _emit(progress, 3, "dither", f"dithering ({opts.dither.value})")
    token.check()

    ink = _dither(toned, opts)
    now = time.perf_counter()
    timings["dither"] = (now - started) * 1000 - timings["decode"] - timings["tone"]

    _emit(progress, 4, "done", f"{ink.shape[1]}x{ink.shape[0]} dots")
    timings["total"] = (now - started) * 1000

    return ConversionResult(ink=ink, options=opts, source=label, timings=timings)


def convert_bytes(
    data: bytes,
    options: ConvertOptions | None = None,
    *,
    name: str = "<bytes>",
    progress: ProgressFn | None = None,
    cancel: CancellationToken | None = None,
    cache_key: str | None = None,
) -> ConversionResult:
    """Convenience wrapper for in-memory data (used by the GUI upload path)."""
    del name  # kept in the signature for symmetry / future logging
    return convert(data, options, progress=progress, cancel=cancel, cache_key=cache_key)


def probe(source: Source) -> dict[str, Any]:
    """Cheap metadata read that does not decode pixels."""
    image, label = _open_source(source)
    return {
        "name": label,
        "format": image.format,
        "mode": image.mode,
        "width": image.width,
        "height": image.height,
        "has_transparency": image.mode in ("RGBA", "LA") or "transparency" in image.info,
    }


def safe_convert(
    source: Source,
    options: ConvertOptions | None = None,
    **kwargs: Any,
) -> tuple[ConversionResult | None, ThermalDotsError | None]:
    """Convert and swallow domain errors - handy for batch loops and the GUI."""
    try:
        return convert(source, options, **kwargs), None
    except ThermalDotsError as error:
        return None, error
