"""Value objects shared by the pipeline, exporters and front-ends."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from enum import Enum, StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from . import exporters
from .errors import InvalidOptionsError

__all__ = [
    "PAPER_WIDTH_DOTS",
    "RENDER_WIDTH_MAX",
    "UPSCALE_MAX",
    "ConversionResult",
    "ConvertOptions",
    "DitherMode",
    "OutputFormat",
    "Paper",
    "ScaleMode",
    "StageEvent",
    "parse_upscale",
    "resolve_upscale",
]

# Raster exports may repeat each dot up to this many times.  The cap keeps a
# 1-bit BMP at a sane size (384 * 16 = 6144 dots wide) while still covering
# "match my original photo" for images up to roughly 6K wide.
UPSCALE_MAX = 16

# Screen exports may render up to this many dots wide.  The bitmap is still
# 1-bit, so this is about detail for a display/design asset, not for a print
# head; ESC/POS and text output refuse the option entirely.
RENDER_WIDTH_MAX = 8192


def parse_upscale(value: str | int | None) -> int | None:
    """Parse an upscale setting: ``None`` means ``auto``, otherwise 1..16."""
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        factor = value
    else:
        text = str(value).strip().lower()
        if text == "auto":
            return None
        try:
            factor = int(text)
        except ValueError:
            raise InvalidOptionsError(
                f"upscale must be a whole number from 1 to {UPSCALE_MAX}, or 'auto'."
            ) from None
    if not 1 <= factor <= UPSCALE_MAX:
        raise InvalidOptionsError(
            f"upscale must be between 1 and {UPSCALE_MAX}, or 'auto'."
        )
    return factor


def resolve_upscale(requested: int | None, dot_width: int, source_width: int) -> int:
    """Turn a parsed setting into a factor.

    ``auto`` picks the whole-number factor whose output width is closest to the
    source image's pixel width, clamped to 1..``UPSCALE_MAX``.  It is about
    matching the file size you started with, not recovering detail: the dots
    are still the printer's dots.
    """
    if requested is not None:
        return requested
    if dot_width <= 0:
        return 1
    factor = round(source_width / dot_width)
    return max(1, min(UPSCALE_MAX, factor))


class Paper(StrEnum):
    MM58 = "58mm"
    MM80 = "80mm"
    CUSTOM = "custom"

    @classmethod
    def parse(cls, value: Paper | str) -> Paper:
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower().replace(" ", "")
        aliases = {
            "58": cls.MM58,
            "58mm": cls.MM58,
            "384": cls.MM58,
            "80": cls.MM80,
            "80mm": cls.MM80,
            "576": cls.MM80,
            "custom": cls.CUSTOM,
        }
        try:
            return aliases[text]
        except KeyError:
            raise InvalidOptionsError(
                f"Unknown paper size {value!r}.", hint="Use 58, 80 or custom."
            ) from None


PAPER_WIDTH_DOTS: dict[Paper, int] = {
    Paper.MM58: 384,
    Paper.MM80: 576,
}


class DitherMode(StrEnum):
    BAYER4 = "bayer4"
    BAYER8 = "bayer8"
    ATKINSON = "atkinson"
    FLOYD_STEINBERG = "fs"
    HALFTONE = "halftone"
    MEAN = "mean"
    NONE = "none"

    @classmethod
    def parse(cls, value: DitherMode | str) -> DitherMode:
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower().replace("_", "-")
        aliases = {
            "bayer": cls.BAYER4,
            "bayer4": cls.BAYER4,
            "bayer-4": cls.BAYER4,
            "bayer8": cls.BAYER8,
            "bayer-8": cls.BAYER8,
            "atkinson": cls.ATKINSON,
            "fs": cls.FLOYD_STEINBERG,
            "floyd": cls.FLOYD_STEINBERG,
            "floyd-steinberg": cls.FLOYD_STEINBERG,
            "floydsteinberg": cls.FLOYD_STEINBERG,
            "halftone": cls.HALFTONE,
            "cluster": cls.HALFTONE,
            "mean": cls.MEAN,
            "threshold": cls.MEAN,
            "none": cls.NONE,
        }
        try:
            return aliases[text]
        except KeyError:
            options = ", ".join(m.value for m in cls)
            raise InvalidOptionsError(
                f"Unknown dither mode {value!r}.", hint=f"Choose one of: {options}."
            ) from None


class ScaleMode(StrEnum):
    FIT = "fit"
    FILL = "fill"
    STRETCH = "stretch"

    @classmethod
    def parse(cls, value: ScaleMode | str) -> ScaleMode:
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        for mode in cls:
            if mode.value == text:
                return mode
        raise InvalidOptionsError(
            f"Unknown scale mode {value!r}.", hint="Use fit, fill or stretch."
        )


class OutputFormat(StrEnum):
    PNG = "png"
    BMP = "bmp"
    ESCPOS = "bin"
    TEXT = "txt"

    @classmethod
    def parse(cls, value: OutputFormat | str) -> OutputFormat:
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower().lstrip(".")
        aliases = {
            "png": cls.PNG,
            "bmp": cls.BMP,
            "bin": cls.ESCPOS,
            "escpos": cls.ESCPOS,
            "esc/pos": cls.ESCPOS,
            "txt": cls.TEXT,
            "text": cls.TEXT,
            "ascii": cls.TEXT,
        }
        try:
            return aliases[text]
        except KeyError:
            raise InvalidOptionsError(
                f"Unknown output format {value!r}.", hint="Use png, bmp, bin or txt."
            ) from None

    @property
    def suffix(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ConvertOptions:
    """Everything that influences the produced dots, and nothing else."""

    paper: Paper = Paper.MM58
    width_dots: int | None = None
    dither: DitherMode = DitherMode.BAYER4
    threshold: int = 128
    auto_threshold: bool = True
    gamma: float = 1.0
    brightness: int = 0
    contrast: float = 1.0
    invert: bool = False
    scale: ScaleMode = ScaleMode.FIT
    rotate: int = 0
    margin: int = 0
    border: bool = False
    max_height_dots: int | None = None
    max_source_pixels: int = 120_000_000
    render_width: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "paper", Paper.parse(self.paper))
        object.__setattr__(self, "dither", DitherMode.parse(self.dither))
        object.__setattr__(self, "scale", ScaleMode.parse(self.scale))

        if self.render_width is not None and not 8 <= self.render_width <= RENDER_WIDTH_MAX:
            raise InvalidOptionsError(
                f"render_width must be between 8 and {RENDER_WIDTH_MAX}, "
                f"got {self.render_width}."
            )
        width = self.resolved_width()
        if self.render_width is None and not 8 <= width <= 2048:
            raise InvalidOptionsError(
                f"width_dots must be between 8 and 2048, got {width}."
            )
        if (
            self.render_width is None
            and self.width_dots is not None
            and self.paper is not Paper.CUSTOM
            and self.paper in PAPER_WIDTH_DOTS
            and self.width_dots != PAPER_WIDTH_DOTS[self.paper]
        ):
            raise InvalidOptionsError(
                f"width_dots={self.width_dots} conflicts with paper={self.paper.value} "
                f"({PAPER_WIDTH_DOTS[self.paper]} dots). Use paper='custom' to override."
            )
        if not 0 <= self.threshold <= 255:
            raise InvalidOptionsError("threshold must be between 0 and 255.")
        if not 0.1 <= self.gamma <= 5.0:
            raise InvalidOptionsError("gamma must be between 0.1 and 5.0.")
        if not -255 <= self.brightness <= 255:
            raise InvalidOptionsError("brightness must be between -255 and 255.")
        if not 0.1 <= self.contrast <= 4.0:
            raise InvalidOptionsError("contrast must be between 0.1 and 4.0.")
        if self.rotate not in (0, 90, 180, 270):
            raise InvalidOptionsError("rotate must be one of 0, 90, 180, 270.")
        if self.margin < 0:
            raise InvalidOptionsError("margin cannot be negative.")
        if self.margin * 2 >= width - 8:
            raise InvalidOptionsError(
                f"margin={self.margin} leaves no room inside width={width} dots."
            )
        if self.max_height_dots is not None and self.max_height_dots < 1:
            raise InvalidOptionsError("max_height_dots must be positive when set.")
        if self.max_source_pixels < 1:
            raise InvalidOptionsError("max_source_pixels must be positive.")

    def resolved_width(self) -> int:
        if self.render_width is not None:
            return self.render_width
        if self.width_dots is not None:
            return self.width_dots
        try:
            return PAPER_WIDTH_DOTS[self.paper]
        except KeyError:
            raise InvalidOptionsError(
                "paper='custom' requires width_dots.", hint="Pass an explicit dot width."
            ) from None

    @property
    def inner_width(self) -> int:
        """Usable width in dots after margins and the optional border."""
        frame = 1 if self.border else 0
        return self.resolved_width() - 2 * self.margin - 2 * frame

    def replace(self, **changes: Any) -> ConvertOptions:
        data = self.to_dict()
        data.update(changes)
        return ConvertOptions.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            data[field.name] = value.value if isinstance(value, Enum) else value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConvertOptions:
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise InvalidOptionsError(f"Unknown option(s): {', '.join(sorted(unknown))}.")
        return cls(**{k: v for k, v in data.items() if v is not None or k == "width_dots"})


@dataclass(frozen=True, slots=True)
class StageEvent:
    """Progress heartbeat emitted between pipeline stages."""

    stage: str
    index: int
    total: int
    message: str = ""

    @property
    def fraction(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.index / self.total)


ProgressFn = Callable[[StageEvent], None]


@dataclass(slots=True)
class ConversionResult:
    """The finished bitmap plus enough metadata to reproduce it."""

    ink: NDArray[np.bool_]
    options: ConvertOptions
    source: str
    timings: dict[str, float]

    @property
    def width(self) -> int:
        return int(self.ink.shape[1])

    @property
    def height(self) -> int:
        return int(self.ink.shape[0])

    @property
    def row_bytes(self) -> int:
        return (self.width + 7) // 8

    @property
    def raster_bytes(self) -> int:
        return self.row_bytes * self.height

    @property
    def ink_ratio(self) -> float:
        return float(self.ink.mean()) if self.ink.size else 0.0

    @property
    def total_ms(self) -> float:
        """Measured end-to-end time.

        ``timings`` also carries a ``"total"`` entry, so summing the whole dict
        would count it twice - prefer the explicit measurement and fall back to
        the stage sum only when it is absent.
        """
        if "total" in self.timings:
            return self.timings["total"]
        return sum(self.timings.values())

    def to_pil(self):  # type: ignore[no-untyped-def]
        from .bits import ink_to_pil

        return ink_to_pil(self.ink)

    def png_bytes(self, compress_level: int = 6, upscale: int = 1) -> bytes:
        return exporters.png_bytes(
            self.ink, compress_level=compress_level, upscale=upscale
        )

    def bmp_bytes(self, upscale: int = 1) -> bytes:
        return exporters.bmp_bytes(self.ink, upscale=upscale)

    def escpos_bytes(
        self,
        *,
        init: bool = True,
        feed_lines: int = 3,
        cut: bool = False,
        fragment_rows: int = 960,
    ) -> bytes:
        return exporters.escpos_bytes(
            self.ink, init=init, feed_lines=feed_lines, cut=cut, fragment_rows=fragment_rows
        )

    def half_blocks(self, max_width: int = 48) -> str:
        return exporters.half_block_text(self.ink, max_width=max_width)

    def describe(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "row_bytes": self.row_bytes,
            "raster_bytes": self.raster_bytes,
            "ink_ratio": round(self.ink_ratio, 4),
            "options": self.options.to_dict(),
            "timings_ms": {k: round(v, 2) for k, v in self.timings.items()},
        }

    def physical_size_mm(self, dpi: int = 203) -> tuple[float, float]:
        return (self.width / dpi * 25.4, self.height / dpi * 25.4)

    @staticmethod
    def estimated_print_seconds(raster_bytes: int, bits_per_second: float = 40_000) -> float:
        return math.ceil(raster_bytes * 8 / bits_per_second * 10) / 10
