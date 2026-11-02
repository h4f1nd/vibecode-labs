"""Desktop UI package (optional: requires the ``gui`` extra)."""

from __future__ import annotations

__all__ = ["main"]


def main(*, debug: bool = False, width: int = 1180, height: int = 820) -> None:
    from .app import main as _main

    _main(debug=debug, width=width, height=height)
