"""User-facing errors.

Every failure the CLI or GUI shows must be a ``DotDatError`` with a safe
``message`` and an actionable ``hint``. Tracebacks never reach the user.
"""

from __future__ import annotations


class DotDatError(Exception):
    """Base class for every expected failure."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class NotADatFile(DotDatError):
    """The file does not carry the Clarion 2.x DAT signature."""


class CorruptDatFile(DotDatError):
    """The header is structurally invalid."""


class TruncatedDatFile(DotDatError):
    """The header describes more data than the file contains."""


class QueryError(DotDatError):
    """A filter expression or field name is invalid."""


class ExportError(DotDatError):
    """An export target cannot be written."""


class OutputExistsError(DotDatError):
    """The destination exists and --force was not supplied."""
