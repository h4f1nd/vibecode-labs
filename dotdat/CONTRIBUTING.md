# Contributing

Thanks for helping DOTDAT read old tables without damaging them. This project is
small on purpose: one parser, one exporter layer, one CLI and one GUI.

## Setup

```powershell
git clone <your-fork>
cd dotdat
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
.venv\Scripts\activate
```

Python 3.11 or newer is required. Development happens on Windows 11 with Python
3.14; Linux and macOS should work for the CLI, but the desktop GUI uses the
WebView2 backend on Windows and GTK/Qt elsewhere.

## Workflow

1. Open an issue or describe the change before large work.
2. Add or update a test that fails for the right reason.
3. Make the smallest change that passes it.
4. Run the four gates below.
5. Update documentation if behaviour or output changed.
6. Open a pull request using the template.

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests benchmarks
.venv\Scripts\mypy src
node --check src\dotdat\ui\web\app.js
```

Real-data coverage is opt-in:

```powershell
$env:DOTDAT_REFERENCE = "C:\path\to\reference\tables"
.venv\Scripts\python -m pytest tests/test_realdata.py
```

Without the environment variable those tests skip, so contributors without the
reference tables can still work.

## Reference data policy

- Never commit `.DAT`, `.DBF`, `.K01`, `.MEM` or exported customer data.
- Never modify a source table. Tests open them read-only.
- Do not add a fixture copied from a real table; build a synthetic one with
  `tests/datbuilder.py` instead.
- Report the file name and structural numbers, not personal data, in issues.

## Clarion Viewer parity

DOTDAT is a **functional copy of Clarion Viewer's** read-only browser, produced
by black-box observation. The rules are strict:

- Run the reference application only as a user. Do not decompile it, inspect its
  memory, or extract resources.
- Record what is displayed (view, column, formatting, timing) and the table that
  demonstrates it. Never record customer data.
- Reimplement the behaviour in new code. Never copy code, assets, help text,
  icons, language packs or registration logic.
- Do not guess unobservable labels. DOTDAT prints the `0x0030` key type as hex
  because Clarion's `NOCASE` / `OPT` / `DUP` flags cannot be attributed from the
  file.
- Update [docs/CLAVIEW.md](docs/CLAVIEW.md) in the same change when parity, a
  deliberate difference or a reference measurement changes.

## Adding a field type

1. Add the decoder to `src/dotdat/codec.py`.
2. Decide how it behaves in `display_value`, JSON and SQL output.
3. Extend `tests/datbuilder.py` so it can encode the type.
4. Add a synthetic parse test and an export test.
5. Update `docs/FORMAT.md` and the limitations list if the type is not covered
   by real-world fixtures.

Arrays return raw bytes by design. Do not guess element descriptors that the
format revision does not expose.

## Changing the filter language

The grammar lives in `src/dotdat/query.py` and is documented in
`docs/USAGE.md`. If you add an operator:

- parse it in `_PATTERN`;
- compile it in `_compile_one`;
- test quoted values, case-insensitivity and the error message;
- keep the CLI and GUI in sync automatically (both call `compile_filters`).

## Changing an export

Every writer receives rows from `DatFile.iter_records`. Keep it streaming; do not
call `list()` on the iterator unless the feature inherently needs all rows.
Preserve:

- UTF-8 output and `\n` line endings;
- a header row for CSV, TXT, HTML, XML and XLSX;
- JSON objects for JSON/JSONL;
- a runnable SQL script;
- the temp-file-and-rename sequence.

Tests assert that a cancelled export leaves no file behind.

## Style

- Type hints on every public function; `mypy --strict`.
- Frozen dataclasses for parsed structures.
- Raise `DotDatError` subclasses, not bare exceptions, for expected failures.
- User-facing messages: imperative, one line, with a hint when the user can fix
  it.
- Documentation: task-first and plain. Define jargon on first use. Keep the
  README quick start short enough to follow without prior knowledge.
- No new dependencies unless they remove a large amount of code. The parser and
  exporters are standard library only; `openpyxl` is the one data dependency.
- GUI: build nodes with `textContent`. Table data is untrusted.

## Writing documentation

DOTDAT has two audiences. Keep them separate:

- `README.md` and `docs/USAGE.md` are for someone who has never opened a
  database file. Start with the desktop app, use numbered steps and plain words,
  and explain a term the first time it appears. "Open, look, filter, export"
  should fit in one screen.
- `docs/FORMAT.md`, `docs/ARCHITECTURE.md` and `docs/PLAN.md` are for
  maintainers. Precise offsets, byte layouts and trade-offs belong there.
- `docs/CLAVIEW.md` is the parity record. Keep it factual, cite the table and
  measurement behind a claim, and never present an observation as a promise
  about other Clarion Viewer versions.

When a button, option or message changes, update the beginner instructions in
the same change. Keep command examples runnable and use English only. There are
no screenshots yet; describe what the user sees instead.

## Changing the frozen build

`build/launcher.py` and `build/build.ps1` are part of the product, not a side
script. Preserve these behaviours:

- the exe keeps the Windows console subsystem, so a shell waits for it and
  `$LASTEXITCODE` is correct;
- a no-argument launch opens the GUI, because Nuitka does not set `sys.frozen`;
- a GUI launch from Explorer hides its private console, but a launch from a
  terminal must not hide the terminal window;
- the standalone folder contains `dotdat/ui/web/*`.

After changing either file, rebuild and test `doctor`, a piped `rows` command,
an export to a bad destination (exit 2), and a double-click launch.

## Commit messages

Use a short imperative subject and explain the why in the body.

```text
Verify the deleted status bit against a table with known deletions

The header count alone is not enough: active records also carry status 0x05.
Only 0x10 is the deleted flag. Added a synthetic case and a real-data check.
```

## License

By contributing you agree that your work is released under the MIT license in
[LICENSE](LICENSE).
