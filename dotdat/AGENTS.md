# AGENTS.md

Instructions for AI coding agents working in this repository. Humans are welcome
to read it too; [CONTRIBUTING.md](CONTRIBUTING.md) has the same rules with more
prose.

Project: `dotdat` — a read-only viewer and exporter for legacy **Clarion 2.x
`.DAT`** tables. It opens a table, shows its header, structure, keys and records,
and exports to CSV, TXT, JSON, JSONL, HTML, XML, SQL or XLSX. It never writes to
the source file.

DOTDAT is a **functional copy of Clarion Viewer's** read-only browser, built by
black-box reverse engineering. The four views, field formatting, key listing and
date rendering follow the reference; the code is new. `docs/CLAVIEW.md` is the
parity record.

## Commands

Copy these exactly. Windows PowerShell, run from **this folder**
(`vibecode-labs\dotdat`), virtualenv at `.venv`.

```text
setup:    uv venv .venv; uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
test:     .venv\Scripts\python -m pytest
realdata: $env:DOTDAT_REFERENCE="C:\path\to\reference\tables"; .venv\Scripts\python -m pytest
lint:     .venv\Scripts\ruff check src tests benchmarks
types:    .venv\Scripts\mypy src
js:       node --check src\dotdat\ui\web\app.js
bench:    .venv\Scripts\python benchmarks\bench_read.py
run cli:  .venv\Scripts\dotdat.exe info <file.dat>
run gui:  .venv\Scripts\dotdat.exe gui
run exe:  build\nuitka\dotdat.dist\dotdat.exe gui
dbl-click: build\nuitka\dotdat.dist\dotdat.exe (no arguments) opens the GUI
wheel:    uv build --wheel --out-dir build\wheel
exe:      powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstall
```

All of `test`, `lint`, `types` and `js` must pass before a change is considered
done. Real-data tests are skipped when `DOTDAT_REFERENCE` does not point at the
reference folder.

The built exe is a console-subsystem program so shells wait, pipes work and exit
codes are reliable. `build/launcher.py` hides the private console for GUI-only
launches and routes a no-argument start to `gui` because Nuitka does not set
`sys.frozen`.

## Repo map

| Path | Responsibility | Read it when |
|---|---|---|
| `src/dotdat/models.py` | Immutable header, field, key, row, page and info dataclasses | Changing anything the CLI or GUI displays |
| `src/dotdat/codec.py` | LONG, REAL, STRING, BCD, date and time decoders | Changing value rendering |
| `src/dotdat/datfile.py` | Read-only mmap reader, schema parsing, paging, sorting | Changing how records are read |
| `src/dotdat/query.py` | Filter parser and predicate compiler | Adding an operator |
| `src/dotdat/exporter.py` | Streaming writers and atomic replace | Changing an export byte |
| `src/dotdat/cli.py` | Typer commands, Rich output, error exit code 2 | Adding or renaming a flag |
| `src/dotdat/errors.py` | `DotDatError` and subclasses with `message`/`hint` | Adding a failure mode |
| `src/dotdat/ui/app.py` | pywebview window and JS bridge | Changing the GUI API |
| `src/dotdat/ui/web/` | `index.html`, `style.css`, `app.js`; no build step | Changing the GUI |
| `tests/datbuilder.py` | Synthetic DAT writer used by the suite | Adding fixtures or a format case |
| `tests/test_realdata.py` | Checks against the 37-table reference set | Verifying header/deleted semantics |
| `build/` | Nuitka script and frozen entry point | Packaging |
| `docs/` | Usage, architecture, format, plan, glossary, Clarion Viewer parity | Before changing behaviour |

## Invariants — never break these

1. **Read-only.** Source `.DAT` files are opened with `rb` and memory-mapped with
   `ACCESS_READ`. There is no write path. Exports refuse to target the source
   file. Do not "repair" or rewrite a table.
2. **Layout.** The header is 85 bytes (`37 + 48`), a field descriptor is 27 bytes,
   a key head is 19 bytes, a key part is 6 bytes, and a record is a 5-byte
   header plus the payload. These sizes are guarded by
   `tests/test_datfile.py` and `tests/datbuilder.py`.
3. **Record payload.** Field offsets are relative to `record_start + 5`, not to
   the start of the record.
4. **Deleted flag.** `status & 0x10` means deleted. Other bits are not deleted.
   A reference table with known deletions is the regression fixture; every
   record's status bit is checked against the header count.
5. **Field names.** Stored names carry the file prefix (`SMP:ACCOUNT`). The
   display name strips it (`ACCOUNT`); `raw_name` keeps the original. Both spellings
   resolve in filters and `--fields`.
6. **BCD.** The high nibble of the first byte is the sign (8 or 9 = negative);
   all remaining nibbles are digits; the value is scaled by `10**decimals`.
7. **Dates and times.** Clarion day 0 is invalid; the epoch is 1800-12-28. Time
   is centiseconds since midnight. Values outside the range render as
   "not recorded".
8. **Atomic exports.** Write to `.<name>.<pid>.tmp` in the destination folder,
   then `os.replace`. A cancelled or failed export must leave no output and no
   temporary file. `tests/test_exporter.py` enforces this.
9. **Error contract.** Expected failures are `DotDatError` with a one-line
   `message` and an actionable `hint`; the CLI exits 2 and never prints a
   traceback. Do not leak raw `struct.error` or `OSError` messages.
10. **Bridge contract.** Every pywebview `Api` method stays positionally callable
    and lock-free where noted. `cancel()` must not take the table lock, or it
    deadlocks during an export. `tests/test_ui_api.py` pins the signatures.
11. **No third-party format library.** The parser is pure Python. TPS libraries
    and Clarion runtime DLLs are out of scope.
12. **Clean-room copy.** DOTDAT is a functional copy of Clarion Viewer's
    read-only browser. Reproduce observed behaviour only. Do not copy code,
    assets, help text, language packs, icons, serial/nag logic or decompiled
    output from Clarion Viewer or Clarion; the reference application is
    inspected only as a black box. `docs/CLAVIEW.md` is the parity record and
    must be updated when a view, column, format or reference measurement
    changes.
13. **Frozen launch.** The exe keeps the console subsystem. Do not switch back
    to `attach` or a GUI subsystem: shells would stop waiting and truncate piped
    output. A no-argument launch must open the GUI, and a GUI launch from
    Explorer must not leave a console window behind.

## Conventions

- Python 3.11+ syntax, `from __future__ import annotations`, full type hints.
  `mypy --strict` on `src`.
- Line length 100. Ruff rules `E F I UP B SIM RUF`.
- Frozen, slotted dataclasses for parsed structures.
- User-facing strings are English, short, and say what to do next. No emoji.
- Documentation is task-first. `README.md` and `docs/USAGE.md` must stay
  understandable to someone who has never used a database tool: open, look,
  filter, export. Put format internals in `docs/FORMAT.md`, not in the quick
  start. Prefer "row" over "record" in beginner sections and define jargon on
  first use.
- `docs/CLAVIEW.md` is the single source of truth for the Clarion Viewer
  comparison. Keep claims factual and tied to the reference tables; describe
  deliberate differences instead of hiding them.
- GUI JavaScript is plain ES2020, no framework and no build step. Build DOM with
  `textContent`, never with interpolated HTML from table data.
- Tests use synthetic tables by default. Real tables are read-only and never
  committed.
- Keep changes focused. If a change alters an invariant, update this file, the
  docs and a test in the same commit.

## Before you finish

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests benchmarks
.venv\Scripts\mypy src
node --check src\dotdat\ui\web\app.js
```

If you touched the parser, also run the real-data suite:

```powershell
$env:DOTDAT_REFERENCE = "C:\path\to\reference\tables"
.venv\Scripts\python -m pytest tests/test_realdata.py
```
