# Third-party notices

DOTDAT is MIT licensed. It depends on the following packages at runtime or while
building. No source code, assets, help text, language packs, icons, serial/nag
logic or decompiled material from Clarion Viewer, Clarion, or Scalabium Software
is included.

## Clarion Viewer (reference application)

DOTDAT is a functional copy of the read-only browser in Scalabium's Clarion
Viewer, produced by observing the original program as a black box. Clarion
Viewer is not a dependency: it is not bundled, linked, called at runtime or
redistributed. No Clarion Viewer code, assets, help text, icons, language packs,
serial/nag logic or decompiled output is included; only the observable behaviour
was reproduced. The comparison is recorded in
[docs/CLAVIEW.md](docs/CLAVIEW.md).

## Runtime

| Package | Used for | License |
|---|---|---|
| [Typer](https://typer.tiangolo.com/) | CLI commands | MIT |
| [Click](https://click.palletsprojects.com/) | CLI runtime under Typer | BSD-3-Clause |
| [Rich](https://rich.readthedocs.io/) | Terminal tables, panels and progress | MIT |
| [openpyxl](https://openpyxl.readthedocs.io/) | XLSX export | MIT |
| [et-xmlfile](https://foss.heptapod.net/openpyxl/et-xmlfile) | XML writer used by openpyxl | MIT |
| [pywebview](https://pywebview.flowrl.com/) | Desktop window and JS bridge (GUI extra) | BSD-3-Clause |
| [pythonnet](https://pythonnet.github.io/) | .NET bridge for the Windows WebView2 backend | MIT |
| [clr-loader](https://github.com/pythonnet/clr-loader) | .NET runtime loader | MIT |
| [cffi](https://cffi.readthedocs.io/) | Foreign-function support | MIT |
| [typing-extensions](https://typing-extensions.readthedocs.io/) | Backports for older Pythons | PSF-2.0 |

The Microsoft Edge **WebView2 runtime** is a system component on Windows 11. It
is not redistributed with DOTDAT. On other platforms pywebview uses the native
GTK/Qt web engine.

## Development and build

| Package | Used for | License |
|---|---|---|
| [pytest](https://pytest.org/) | Test runner | MIT |
| [Ruff](https://docs.astral.sh/ruff/) | Linter and formatter | MIT |
| [mypy](https://mypy-lang.org/) | Static type checking | MIT |
| [Nuitka](https://nuitka.net/) | Standalone Windows build | Apache-2.0 |
| [uv](https://docs.astral.sh/uv/) | Environment and package management | Apache-2.0 / MIT |

Nuitka may download a C compiler and dependency-cache components during the
build. Those are build-time tools, not part of the DOTDAT source license.

The standalone folder also contains the Python runtime, Typer, Rich, openpyxl,
pywebview, pythonnet, clr-loader and the WebView2 loader. The Edge WebView2
runtime itself is supplied by Windows and is not redistributed. DOTDAT adds no
network client and no telemetry library.

## Trademarks

Clarion is a trademark of its respective owner. DOTDAT is an independent,
unofficial reader and is not affiliated with or endorsed by Clarion or
Scalabium Software. Product names are used only to describe compatibility.
