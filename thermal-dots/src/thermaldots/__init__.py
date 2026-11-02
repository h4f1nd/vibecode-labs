"""thermal-dots - images to 1-bit dots for 58/80 mm thermal printers."""

from __future__ import annotations

__version__ = "1.0.0"

from .errors import (
    ConversionCancelled,
    ImageTooLargeError,
    InvalidOptionsError,
    OutputError,
    OutputInUseError,
    SourceNotFoundError,
    ThermalDotsError,
    UnsupportedImageError,
)
from .models import (
    ConversionResult,
    ConvertOptions,
    DitherMode,
    OutputFormat,
    Paper,
    ScaleMode,
    StageEvent,
)
from .pipeline import CancellationToken, convert, convert_bytes, probe
from .profiles import PAPERS, PRESETS, get_paper, list_papers

__all__ = [
    "PAPERS",
    "PRESETS",
    "CancellationToken",
    "ConversionCancelled",
    "ConversionResult",
    "ConvertOptions",
    "DitherMode",
    "ImageTooLargeError",
    "InvalidOptionsError",
    "OutputError",
    "OutputFormat",
    "OutputInUseError",
    "Paper",
    "ScaleMode",
    "SourceNotFoundError",
    "StageEvent",
    "ThermalDotsError",
    "UnsupportedImageError",
    "__version__",
    "convert",
    "convert_bytes",
    "get_paper",
    "list_papers",
    "probe",
]
