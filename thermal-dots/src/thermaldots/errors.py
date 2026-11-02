"""Typed error hierarchy.

Every error carries a short message that is safe to show to a user plus an
optional actionable hint.  Tracebacks belong in the log file, never in the UI.
"""

from __future__ import annotations


class ThermalDotsError(Exception):
    """Base class for every error this package raises deliberately."""

    default_message = "Something went wrong."
    default_hint: str | None = None

    def __init__(self, message: str | None = None, *, hint: str | None = None) -> None:
        self.message = message or self.default_message
        self.hint = hint if hint is not None else self.default_hint
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message}\nHint: {self.hint}"
        return self.message

    def to_dict(self) -> dict[str, str | None]:
        return {
            "error": type(self).__name__,
            "message": self.message,
            "hint": self.hint,
        }


class InvalidOptionsError(ThermalDotsError):
    default_message = "Invalid conversion options."
    default_hint = "Check the paper width, dither mode and tone values."


class SourceNotFoundError(ThermalDotsError):
    default_message = "The source file could not be found."
    default_hint = "Check the path, or drag the file into the app."


class UnsupportedImageError(ThermalDotsError):
    default_message = "This file is not an image that can be read."
    default_hint = "Supported: PNG, JPEG, BMP, GIF, WEBP, TIFF. For HEIC install 'thermal-dots[heif]'."


class ImageTooLargeError(ThermalDotsError):
    default_message = "The image is too large to process safely."
    default_hint = "Downscale the source image, or raise ConvertOptions.max_source_pixels."


class OutputError(ThermalDotsError):
    default_message = "Could not write the output file."
    default_hint = "Check that the folder exists and that you have write permission."


class OutputInUseError(ThermalDotsError):
    default_message = "The output file is open in another application."
    default_hint = "Close the file (or the print app that holds it) and try again."


class ConversionCancelled(ThermalDotsError):
    default_message = "Conversion cancelled."
    default_hint = None
