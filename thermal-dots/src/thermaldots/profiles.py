"""Paper and device constants plus ready-made presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ConvertOptions, DitherMode, Paper, ScaleMode

__all__ = ["PAPERS", "PRESETS", "PaperProfile", "get_paper", "list_papers"]

DPI = 203  # dots per inch, the near-universal value for 58/80 mm thermal heads


@dataclass(frozen=True, slots=True)
class PaperProfile:
    paper: Paper
    label: str
    width_dots: int
    printable_mm: float
    typical_baud: int

    @property
    def row_bytes(self) -> int:
        return (self.width_dots + 7) // 8

    @property
    def dot_mm(self) -> float:
        return round(25.4 / DPI, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper": self.paper.value,
            "label": self.label,
            "width_dots": self.width_dots,
            "row_bytes": self.row_bytes,
            "printable_mm": self.printable_mm,
            "dpi": DPI,
        }


PAPERS: dict[Paper, PaperProfile] = {
    Paper.MM58: PaperProfile(
        paper=Paper.MM58,
        label="58 mm (384 dots)",
        width_dots=384,
        printable_mm=48.0,
        typical_baud=9600,
    ),
    Paper.MM80: PaperProfile(
        paper=Paper.MM80,
        label="80 mm (576 dots)",
        width_dots=576,
        printable_mm=72.0,
        typical_baud=19200,
    ),
}


def get_paper(paper: Paper | str) -> PaperProfile:
    key = Paper.parse(paper)
    if key not in PAPERS:
        raise KeyError(f"custom paper has no fixed profile (paper={key.value})")
    return PAPERS[key]


def list_papers() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in PAPERS.values()]


PRESETS: dict[str, dict[str, Any]] = {
    "hacker-bayer": {
        "paper": "58mm",
        "dither": "bayer4",
        "gamma": 1.25,
        "contrast": 1.15,
        "threshold": 128,
        "scale": "fit",
    },
    "photo-floyd": {
        "paper": "58mm",
        "dither": "fs",
        "gamma": 1.1,
        "contrast": 1.0,
        "threshold": 128,
        "scale": "fit",
    },
    "newsprint": {
        "paper": "58mm",
        "dither": "halftone",
        "gamma": 1.2,
        "contrast": 1.2,
        "threshold": 128,
        "scale": "fit",
    },
    "line-art": {
        "paper": "58mm",
        "dither": "mean",
        "gamma": 1.0,
        "contrast": 1.4,
        "threshold": 160,
        "scale": "fit",
    },
    "wide-hacker": {
        "paper": "80mm",
        "dither": "bayer8",
        "gamma": 1.25,
        "contrast": 1.15,
        "threshold": 128,
        "scale": "fit",
    },
    # Clean logo/header asset: no dither texture, no tone curve.  The extra
    # ``render`` key is a GUI hint: selecting this preset also switches the
    # render selector to native.  The CLI ignores it, so
    # `tdots convert logo.png --preset header -f bin` still prints at 80 mm.
    "header": {
        "paper": "80mm",
        "dither": "mean",
        "gamma": 1.0,
        "contrast": 1.0,
        "threshold": 128,
        "scale": "fit",
        "render": "native",
    },
}


def preset_options(name: str) -> ConvertOptions:
    try:
        data = PRESETS[name]
    except KeyError:
        raise KeyError(f"unknown preset {name!r}") from None
    return ConvertOptions(
        paper=Paper.parse(data["paper"]),
        dither=DitherMode.parse(data["dither"]),
        gamma=data["gamma"],
        contrast=data["contrast"],
        threshold=data["threshold"],
        scale=ScaleMode.parse(data["scale"]),
    )
