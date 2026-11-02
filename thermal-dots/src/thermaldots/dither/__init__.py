"""Dithering algorithms.

Every function takes a 2-D ``uint8`` grayscale array (0 = black .. 255 =
white) and returns a 2-D boolean ``ink`` array where ``True`` means the thermal
head fires (a black dot).

No function loops over pixels in Python except the error-diffusion fallbacks,
which are bounded to the output width (384/576 dots) and therefore cheap.
"""

from __future__ import annotations

from .error_diffusion import atkinson, floyd_steinberg
from .halftone import clustered_dot, halftone_dither
from .ordered import bayer_matrix, ordered_dither
from .threshold import mean_threshold, otsu_threshold

__all__ = [
    "atkinson",
    "bayer_matrix",
    "clustered_dot",
    "floyd_steinberg",
    "halftone_dither",
    "mean_threshold",
    "ordered_dither",
    "otsu_threshold",
]
