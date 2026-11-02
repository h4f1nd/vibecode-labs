"""Entry point for the frozen (Nuitka) build.

Nuitka compiles its entry script as a *top-level* module.  ``src/thermaldots/
__main__.py`` cannot be that script: it uses a relative import (``from .cli
import main``) which only works when the file runs as ``python -m thermaldots``.
Compiling it directly produced a binary that crashed on start with::

    ImportError: attempted relative import with no known parent package

This launcher uses an absolute import and mirrors the ``tdots`` console script,
so the frozen binary and ``pip install`` behave identically.
"""

from __future__ import annotations

from thermaldots.cli import main

if __name__ == "__main__":
    main()
