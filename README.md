# vibecode-labs

Two small Windows tools, kept together because they share a style: one job each,
plain Python, honest documentation, no telemetry and no network calls.

| Project | Version | What it does |
|---|---|---|
| [thermal-dots](thermal-dots/README.md) | 1.0.0 | Converts images into exportable 1-bit graphics for 58 mm or 80 mm thermal printers; printing is not supported. |
| [dotdat](dotdat/README.md) | 0.1.0 | Opens legacy Clarion 2.x `.DAT` tables read-only, shows their structure and rows, and exports them. |

Both are **Python 3.11+**, **MIT licensed**, and developed on Windows 11. Each
folder is a complete project with its own `pyproject.toml`, tests, docs and
`LICENSE`; the repository root only adds a shared README, CI and issue
templates.

---

## thermal-dots

Images → export files. It converts images into 1-bit dot graphics and exports
them as PNG, BMP, raw ESC/POS data or text art. Output is 384 dots wide for
58 mm printers or 576 dots wide for 80 mm printers. It includes seven dithering
modes and a desktop preview rendered from the exported bitmap.

**Printing is not implemented.** The app does not connect to a printer or send
print jobs. Raw ESC/POS is an exported file, not a print operation. To print,
open an exported file with separate printer software.

```powershell
git clone https://github.com/h4f1nd/vibecode-labs.git
cd vibecode-labs\thermal-dots
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
.venv\Scripts\tdots.exe convert photo.jpg -o photo_58.png
```

- Full guide: [thermal-dots/README.md](thermal-dots/README.md)
- Every flag: [thermal-dots/docs/USAGE.md](thermal-dots/docs/USAGE.md)

---

## dotdat

A read-only viewer and exporter for Clarion 2.x `.DAT` files. It shows the
header, field structure, keys and rows, detects date columns, and exports to
CSV, TXT, JSON, JSONL, HTML, XML, SQL or XLSX. Source tables are memory-mapped
read-only and are never modified.

DOTDAT is a **functional copy of Clarion Viewer's** read-only browser, built by
**reverse engineering the original as a black box**: the four views, field
formatting, key listing and date display were observed and reimplemented in new
Python code. No Clarion Viewer code, assets, help text, icons, language packs,
serial/nag logic or decompiled output is included. The feature-by-feature
record, evidence and deliberate differences are in
[dotdat/docs/CLAVIEW.md](dotdat/docs/CLAVIEW.md).

```powershell
cd vibecode-labs\dotdat
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
.venv\Scripts\dotdat.exe info "C:\data\SAMPLE.DAT"
.venv\Scripts\dotdat.exe gui
```

- Full guide: [dotdat/README.md](dotdat/README.md)
- Clarion Viewer comparison: [dotdat/docs/CLAVIEW.md](dotdat/docs/CLAVIEW.md)

---

## Repository layout

```text
vibecode-labs/
├─ thermal-dots/     image -> thermal dots (CLI + GUI)
├─ dotdat/           Clarion .DAT viewer/exporter (CLI + GUI)
└─ .github/          CI for both projects, issue and PR templates
```

Each project keeps its own `.gitignore`. The root ignore rules cover the shared
build output, virtualenvs and local database/export files so private tables are
never committed.

## Releases

Prebuilt Windows bundles are attached to GitHub Releases instead of being
committed:

| Tag | Contents |
|---|---|
| `v1.0.0` | `tdots.dist` archive (standalone `tdots.exe`, no Python needed) |
| `dotdat-v0.1.0` | `dotdat.dist` archive (standalone `dotdat.exe`, no Python needed) |

Both executables are console-subsystem programs: a terminal waits for CLI
commands, and a no-argument launch opens the GUI.

## Development

Run the gates from inside the project you changed:

```powershell
cd thermal-dots   # or: cd dotdat

.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests benchmarks
.venv\Scripts\mypy src
```

Then check the GUI script:

```powershell
node --check src\thermaldots\ui\web\app.js   # inside thermal-dots
node --check src\dotdat\ui\web\app.js        # inside dotdat
```

CI runs the same gates on Windows for Python 3.11 and 3.14. The workflows live at
the repository root and are path-filtered, so a change to one project does not
rebuild the other.

## License

MIT. Each project has its own [LICENSE](thermal-dots/LICENSE) file
([dotdat](dotdat/LICENSE)); the dependency and trademark notes are in
[dotdat/THIRD_PARTY_NOTICES.md](dotdat/THIRD_PARTY_NOTICES.md).

DOTDAT is unofficial and is not affiliated with or endorsed by Clarion or
Scalabium Software. Product names are used only to describe compatibility.
