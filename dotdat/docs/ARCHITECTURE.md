# Architecture

DOTDAT is a small layered application: one read-only format engine, one export
layer, and two front ends (Typer CLI and pywebview GUI) that share both.

```
                        +----------------+   +----------------+
                        |    cli.py      |   |   ui/app.py    |
                        |  Typer / Rich  |   |   pywebview    |
                        +-------+--------+   +--------+-------+
                                |                     |
                    +-----------+---------------------+-----------+
                    |                  exporter.py                |
                    |   CSV TXT JSON JSONL HTML XML SQL XLSX     |
                    +-----------+---------------------+-----------+
                                |                     |
                        +-------+--------+   +--------+-------+
                        |   datfile.py   |   |    query.py    |
                        |  mmap + schema |   | filter compiler|
                        +-------+--------+   +--------+-------+
                                |                     |
                        +-------+--------+   +--------+-------+
                        |    codec.py    |   |   models.py    |
                        | value decoding |   | frozen records |
                        +----------------+   +----------------+
```

There is no database engine, no ORM and no runtime dependency on Clarion. The
parser is standard library only.

## Provenance

DOTDAT is a functional copy of Scalabium Clarion Viewer's read-only browser,
built by black-box reverse engineering. The project ran the reference
application on the 37-table set, recorded its four views, column sets,
formatting, date rendering and key listing, then reproduced that behaviour in
new code. No Clarion Viewer code, assets, help text, icons, language packs or
registration logic was used. The comparison, evidence and deliberate differences
are in [CLAVIEW.md](CLAVIEW.md).

Parity material lives at the edges, not in the parser. `DatFile.date_fields()`
mirrors the reference's date display, `FieldDef.significant` and
`FieldDef.decimals` feed the `format` column, and `ui/web/app.js` renders keys
and dates. The reader itself is derived from the DAT layout and the DBF ground
truth, not from the reference program.

## Modules

| Module | Responsibility |
|---|---|
| `models.py` | `DatHeader`, `FieldDef`, `KeyDef`, `RecordRow`, `Page`, `TableInfo`; JSON conversion |
| `codec.py` | LONG, REAL, STRING, PICTURE, BYTE, SHORT, DECIMAL/BCD, dates and times |
| `datfile.py` | Open, validate, parse, memory-map, read, page, sort, count |
| `query.py` | Parse filter expressions and compile one predicate |
| `exporter.py` | Field selection, streaming writers, atomic rename, progress |
| `cli.py` | Commands, Rich rendering, exit code 2, frozen-app GUI launch |
| `ui/app.py` | Window, JavaScript bridge, dialogs, cancellation flag |
| `ui/web/` | Static HTML, CSS and JavaScript; no bundler |
| `errors.py` | `DotDatError` hierarchy with `message` and `hint` |
| `build/launcher.py` | Nuitka entry point, private-console hiding, no-argument GUI routing |

## Read path

1. `DatFile(path)` opens the file with `rb` and maps it with
   `mmap.ACCESS_READ`. The constructor never writes.
2. `_parse()` unpacks the 85-byte header, validates the signature, field count
   and record length, then reads 27-byte field descriptors and the key blocks.
3. It verifies that every field fits inside `record_length - 5`, that the data
   offset is not before the schema, and that
   `data_offset + record_count * record_length <= file size`.
4. `read_record(index)` seeks arithmetically to
   `data_offset + index * record_length`, reads the status byte, skips four
   pointer bytes, then decodes every field from `record_start + 5 + offset`.
5. A decode failure for one field becomes `<invalid:HEX>` in that cell. A
   structural failure aborts the open with a `DotDatError`.

mmap keeps the open cost independent of table size. A table with over a million
rows opens in milliseconds; the OS pages in only the records touched.

## Paging

`DatFile.page(offset, limit, include_deleted, predicate, sort, desc)` returns a
`Page` with rows and the best known total.

- **No predicate, no sort** - total comes from the header (`record_count` or
  `active_count`). If deleted rows are included, or the table has none, rows are
  read by direct index. Otherwise the iterator skips deleted rows and `_take`
  stops after `offset + limit` matches.
- **Predicate** - the iterator scans and the predicate filters. The page reads
  until it has enough rows; `total` is `None` because counting would require a
  second full scan.

  `compile_filters` returns a `Filter` that remembers which fields it touches.
  When the iterator sees one, it decodes only those fields per candidate row,
  tests the predicate, and re-reads the full record only for rows that match.
  A filter on one column of a 12-column table therefore decodes one field per
  row while scanning, not twelve. Hand-written predicates remain supported:
  without a `.fields` hint the full record is decoded.
- **Sort** - every matching row is materialized, sorted by the key, sliced, and
  returned. `total` is the materialized length. This is the one intentionally
  expensive path; the GUI and docs warn about it.

`Page.has_more` uses the total when known, otherwise `len(rows) == limit`.
`Page.to_dict()` is the JSON shape shared by `rows --json` and the bridge.

## Deleted records

The status byte is the first byte of each record. Bit `0x10` is the deleted flag;
other bits observed in the reference data (`0x01`, `0x05`) are not deletion.

- `RecordRow.deleted` is `bool(status & 0x10)`.
- `include_deleted=False` is the default everywhere.
- A reference table with known deletions is the regression fixture: the header
  count matches the status bit on every row.

The header `deleted_count` is trusted for the total of unfiltered active rows.
DOTDAT does not rescan the file on open.

## Names and encoding

Field descriptors store names with the file prefix, for example `SMP:ACCOUNT`.
`DatFile` strips the prefix for display and keeps the raw spelling in
`FieldDef.raw_name`. `resolve_field` accepts either form. This makes
`--fields ACCOUNT` and filters natural while preserving fidelity in `info --json`.

Strings are decoded with the selected code page (default `cp437`) and truncated
at the first NUL. Trailing spaces are removed. Invalid bytes are replaced rather
than raising, so one bad cell cannot block a table.

## Filtering

`query.py` uses one regular expression for the grammar and compiles every
expression into a closure inside a `Filter`. Numeric field types coerce the
right-hand side once at compile time; strings are case-folded for comparison.
`Filter.fields` lists the columns involved, which drives the partial-decode fast
path in `DatFile`.

Malformed expressions, unknown fields and invalid numbers raise `QueryError`
before any record is read. Both front ends surface the same message and hint.

## Exports

`export_table` is the only write path:

1. Validate the format, destination, existence, source collision and Excel row
   cap.
2. Resolve selected fields and compute a known total when possible.
3. Create `.<name>.<pid>.tmp` in the destination folder.
4. Stream rows from `iter_records`, checking the cancel callback before each row.
5. Write the format-specific bytes or workbook.
6. `os.replace(tmp, out)`.
7. On any exception, unlink the temporary file and re-raise.

CSV and TXT use `csv.writer`; JSON/JSONL serialize one row at a time; HTML and XML
escape every value; SQL batches 200 rows per `INSERT`; XLSX uses openpyxl's
write-only mode. Decimal values are rendered as exact strings in JSON and text
formats and as floats in Excel.

## GUI

`ui/app.py` creates a 1280x840 window and a JS API. pywebview calls methods in
order, so every bridge method is positional:

```
initial_state()
load(path, encoding)
close()
page(offset, limit, include_deleted, filters, sort, desc)
export(fmt, path, include_deleted, filters, fields, sort, desc)
cancel()
pick_file()
export_dialog(suggested)
```

`tests/test_ui_api.py` pins those signatures. The bridge holds an `RLock` around
table access. `cancel()` deliberately does not take the lock, because an export
holds it for the whole run; the export callback reads a plain boolean.

The front end boots on `pywebviewready`, calls `initial_state`, and loads the
path passed on the command line if present. It renders with DOM APIs and
`textContent`, never by interpolating table values into HTML. One stale-response
guard (`state.seq`) prevents an older page request from overwriting a newer one.

Display-only helpers stay in the front end. `date_fields` comes from the reader
(see `docs/FORMAT.md`) and the `dates` checkbox renders those columns as
`YYYY-MM-DD` with `Date.UTC(1800, 11, 28)` plus the day count; the cell title
keeps the raw number and the toggle re-renders the current page without a
re-read. Filters, sorting and exports never see the rendered text.

The web assets are loaded from the source tree (or the Nuitka data directory) with
no network access, no CDN and no build step.

## Frozen app startup

The Nuitka build uses `build/launcher.py` because Nuitka compiles its entry script
as a top-level module, while `src/dotdat/__main__.py` uses a relative import. The
launcher mirrors the installed `dotdat` console script.

Two Windows details matter:

1. **Console subsystem.** The exe is built with
   `--windows-console-mode=force`, so PowerShell and `cmd.exe` wait for it,
   pipes work and exit codes are reliable. A plain GUI-subsystem exe returns
   immediately and silently truncates redirected output.
2. **No-argument launch.** Nuitka does not set `sys.frozen`, so the launcher
   appends the `gui` command when `sys.argv` has no arguments. Double-clicking
   and running `dotdat.exe` from a terminal both open the window; CLI commands
   must be named explicitly.
3. **Private console.** For a GUI-only launch the launcher calls
   `GetConsoleProcessList`. If DOTDAT is the only process attached to the
   console, it hides that console window. If a terminal is attached too, it
   leaves the window alone. This avoids a stray console next to the desktop app
   without hiding the user's terminal.

The launcher package is frozen into the standalone folder together with
`dotdat/ui/web/*`; the folder must stay intact.

## Errors

`DotDatError` carries a user-facing `message` and an optional `hint`.
Subclasses identify the category (`NotADatFile`, `CorruptDatFile`,
`TruncatedDatFile`, `QueryError`, `ExportError`, `OutputExistsError`).

- CLI: catches `DotDatError`, prints `error`/`hint`, exits 2.
- GUI: bridge returns `{ok: false, error, hint}`; the toast shows both.
- Unexpected exceptions are bugs and should be fixed, not swallowed.

## Performance notes

- mmap + index arithmetic avoids reading sequential records for paging.
- `read_record` slices small byte ranges; string decoding is per field.
- Filter scans decode only the fields the predicate uses (see
  [Paging](#paging)). On the largest reference table (over a million rows) a
  full scan dropped from roughly 80 seconds to 15-25 seconds.
- Sorting is `O(n log n)` with materialization; avoid it on the largest table
  unless needed.
- Export progress is reported every 1,000 rows (and on the first/last row) to
  keep callback overhead low.

## Gates

| Gate | Command |
|---|---|
| Tests | `.venv\Scripts\python -m pytest` |
| Real data | `$env:DOTDAT_REFERENCE="C:\path\to\reference\tables"; .venv\Scripts\python -m pytest tests/test_realdata.py` |
| Lint | `.venv\Scripts\ruff check src tests benchmarks` |
| Types | `.venv\Scripts\mypy src` |
| JS syntax | `node --check src\dotdat\ui\web\app.js` |
| Wheel | `uv build --wheel --out-dir build\wheel` |
| Exe | `powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstall` |

The suite includes over 150 tests: codec edge cases, synthetic DAT construction
and corruption cases, query compilation, every export format, CLI behaviour,
bridge behaviour, documentation links, and opt-in checks against the 37-table
reference set.

## Safety boundaries

- No code path opens a source `.DAT` for writing.
- Export refuses to use the source path, even with `--force`.
- The GUI has no mutation controls.
- The parser validates before reading records; corrupt files fail closed.
- Real data is never committed; synthetic fixtures are generated in tests.
