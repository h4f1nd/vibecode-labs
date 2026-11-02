"""Entry point for the frozen (Nuitka) build.

Nuitka compiles its entry script as a top-level module. ``src/dotdat/__main__.py``
cannot be that script because it uses a relative import (``from .cli import
main``), which only works under ``python -m dotdat``. This launcher mirrors the
``dotdat`` console script with an absolute import, so the frozen binary and an
installed package behave the same.

The frozen exe uses the console subsystem so that shells wait for it, pipes work
and exit codes are reliable. When it is started from Explorer with no arguments
(or with the ``gui`` command), the private console window is hidden before the
GUI opens. A console shared with a terminal is left alone.
"""

from __future__ import annotations

import sys


def _hide_private_console() -> None:
    """Hide the console window when this process is its only client."""
    if sys.platform != "win32":
        return
    args = sys.argv[1:]
    if args and args[0] != "gui":
        return

    import ctypes

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    hwnd = kernel32.GetConsoleWindow()
    if not hwnd:
        return

    # A console created for this process alone (Explorer double-click) has one
    # attached process. A console shared with cmd.exe/PowerShell has more, and
    # hiding it would hide the user's terminal too.
    pids = (ctypes.c_uint * 2)()
    if kernel32.GetConsoleProcessList(pids, 2) != 1:
        return
    user32.ShowWindow(hwnd, 0)  # SW_HIDE


if __name__ == "__main__":
    _hide_private_console()
    if len(sys.argv) == 1:
        # Nuitka does not set sys.frozen, so route the double-click case here
        # instead of relying on the CLI callback to detect a frozen build.
        sys.argv.append("gui")

    from dotdat.cli import main

    main()
