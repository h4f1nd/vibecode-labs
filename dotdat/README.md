# DOTDAT

```
  ▓▓▓   ▓▓▓  ▓▓▓▓▓ ▓▓▓▓▓  ▓▓▓  ▓▓▓▓▓
  ▓  ▓ ▓  ▓    ▓     ▓   ▓  ▓    ▓
  ▓  ▓ ▓  ▓    ▓     ▓   ▓▓▓▓    ▓
  ▓  ▓ ▓  ▓    ▓     ▓   ▓  ▓    ▓
  ▓▓▓   ▓▓▓    ▓     ▓   ▓  ▓    ▓
```

DOTDAT opens old **Clarion 2.x `.DAT`** database files on a modern Windows PC.
It is a **functional copy of Clarion Viewer**, rebuilt from the original's
observed behaviour: the same four views, field formatting and date display,
without the trial limit. It lets you search the tables and saves what you find
as CSV, Excel, JSON, SQL and other formats.

**DOTDAT is read-only.** It never edits, deletes, repairs or renames your `.DAT`
file. The only files it writes are the exports you ask for.

Part of [vibecode-labs](../README.md); the sibling app is
[thermal-dots](../thermal-dots/README.md), an image-to-thermal-dots converter.

- Opens every table in the reference set; a structurally corrupt file is refused
  with a clear message instead of being guessed at.
- Deleted rows are hidden by default, but you can show them at any time.
- Large tables open quickly because the file is read in place, not copied.
- The desktop window and the command line use the same reader, so results match.
- Exports are written safely: a failed or cancelled export leaves no half file.

---

## Relationship to Clarion Viewer

DOTDAT is a **copy version** of Scalabium's **Clarion Viewer**: a
feature-for-feature reimplementation of its read-only table browser. The plan
was to reproduce the Clarion Viewer experience exactly, and the work was done by
**reverse engineering the original as a black box** — opening real tables,
switching tabs, recording what it showed and how long it took — then writing a
new implementation in Python.

In short: DOTDAT copies the Clarion Viewer *experience*, not the Clarion Viewer
*program*. No code, assets, help text, icons, language packs, serial/nag logic
or decompiled output is included.

| Clarion Viewer view | DOTDAT | What matches |
|---|---|---|
| General Information | **Overview** | File and header facts: rows, fields, keys, sizes, timestamps |
| Table Structure | **Structure** (fields) | Field names, types, offsets, lengths, `format` column |
| Data Grid | **Data** | Same columns and values; date columns shown as dates |
| Keys | **Structure** (keys) | Key names, component fields, field types, `0x0030` key type |

DOTDAT also removes the reference's trial limits: the full table is available
instead of 100 rows, and filtering, sorting, jumping, toggling deleted rows and
exporting are built in.

The full side-by-side comparison, the evidence, the deliberate differences and
the clean-room rules are in [docs/CLAVIEW.md](docs/CLAVIEW.md).

---

## Open your first table

You do not need Python or any setup for this. Use the built app.

1. Open the folder `build\nuitka\dotdat.dist` in this project (or unpack the
   release archive from the repository's Releases page).
2. Double-click **`dotdat.exe`**. A dark window called **DOTDAT** opens.
3. Click **Open .DAT**.
4. Pick a table, for example `C:\data\SAMPLE.DAT`.
5. Click the **Data** tab. Your rows appear.
6. Close the window when you are done. Nothing was changed.

That is the whole basic workflow: **open → look → maybe export → close**.

If you prefer a terminal, `dotdat.exe gui` opens the same window, and
`dotdat.exe gui "C:\path\TABLE.DAT"` opens a table immediately.

### What the tabs show

| Tab | What it is for |
|---|---|
| **Overview** | A summary: how many rows, fields and keys the table has, its size, encoding and last-change time. |
| **Structure** | The field list (names, types, offsets, lengths, number format) and the key definitions, including which fields each key uses. Look here when you need an exact field name for a filter. |
| **Data** | The rows themselves. This is where you browse, filter, sort and export. |

### Why some cells look like dates

Clarion stores a date as a whole number of days since 28 December 1800, so
`DATE` can read `73928`. DOTDAT recognises such columns and shows
`2003-05-26` instead. Hover over the cell to see the stored number. Untick
**dates** above the table to see raw numbers everywhere. Filters and exports
always use the raw numbers, so nothing is changed or lost.

The bar at the bottom shows what DOTDAT is doing, how many rows are shown, and
the version.

### Things you will do most often

| I want to… | Do this |
|---|---|
| Look at another table | **Open .DAT** again. |
| See deleted rows too | Tick **deleted** above the table. |
| See raw date numbers | Untick **dates** above the table. |
| Show more rows at once | Change the **rows** dropdown (50, 100, 500 or 1000). |
| Move through the table | Use **‹ prev** and **next ›**. |
| Jump to a row number | Type a number under **go to record** and click **go**. |
| Sort a column | Click its header once (ascending), again (descending), a third time (file order). |
| Find rows | Type in the **filter** box and press Enter. |
| Save the result | Choose a format, then click **Export**. |

Sorting a very large table (over a million rows) can take a few seconds. That is
normal. The status bar stays busy until it finishes.

---

## Find rows with a filter

The filter box understands short expressions. Type one, press **Enter**, and the
table shows only matching rows. Press **Escape** to clear it.

```text
AREA=01
BALANCE>=1000
NAME~sample
```

- `=` means **equals**.
- `>=`, `>`, `<=`, `<` compare numbers or text.
- `~` means **contains**, and ignores upper/lower case.
- Put several conditions in one line with `;`. **All** of them must match:

```text
AREA=01 ; YEAR=2026 ; BALANCE>=1000
```

- Quote values that contain spaces: `NAME="SAMPLE CUSTOMER"`.
- Field names are not case-sensitive. You can use `ACCOUNT` or the stored
  `SMP:ACCOUNT`; both work.
- Not sure of a field name? Open the **Structure** tab and copy it from there.

Two things surprise people:

- **Dates are numbers, not text.** Clarion stores a day count such as `73928`.
  The table may show `2003-05-26`, but filters use the number
  (`DATE>=73000`). Hover a cell or untick **dates** to see it.
- **Deleted rows are hidden first.** Tick **deleted** if your filter seems to be
  missing rows that you know exist.

The full operator list is in [docs/USAGE.md](docs/USAGE.md#filter-language).

---

## Export your data

1. Open a table and, if you like, apply a filter.
2. Choose a format in the dropdown next to the **Export** button.
3. Click **Export** and choose where to save the file.

An export writes **every matching row**, not only the page you can see. It also
respects the **deleted** checkbox and the current sort order.

| Format | Best for |
|---|---|
| **CSV** | Opening in Excel, LibreOffice, Google Sheets or another database. |
| **TXT** | A simple tab-separated file for scripts and old tools. |
| **JSON** | Sending the data to a modern application. |
| **JSONL** | Very large data, or line-by-line processing. |
| **HTML** | A ready-to-open web page with a scrollable table. |
| **XML** | Older systems that expect XML. |
| **SQL** | Loading the rows into SQLite, MySQL, PostgreSQL and similar. |
| **XLSX** | A real Excel workbook. |

Excel has a hard limit of 1,048,576 rows including the header. DOTDAT refuses an
Excel export that cannot fit and tells you to use CSV or JSONL instead.

Exports are atomic: DOTDAT writes a temporary file and renames it only when the
last row is done. A failed or cancelled export leaves no partial file. Existing
files are never replaced silently; the save dialog asks first.

See [docs/USAGE.md](docs/USAGE.md#export-formats) for the exact value rules.

---

## Run DOTDAT

### The built app (no Python needed)

```powershell
build\nuitka\dotdat.dist\dotdat.exe
```

Double-clicking the exe and running it with no arguments do the same thing: they
open the desktop window. To run a command instead, name it explicitly:

```powershell
build\nuitka\dotdat.dist\dotdat.exe info "C:\data\SAMPLE.DAT"
```

The exe is a normal console program, so PowerShell and `cmd.exe` wait for it,
pipes work, and the exit code is reliable.

If the exe does not exist yet, build it once — see
[Build a standalone Windows exe](#build-a-standalone-windows-exe).

### From source

```powershell
cd vibecode-labs\dotdat
.venv\Scripts\activate
dotdat gui
```

Without activating first:

```powershell
.venv\Scripts\dotdat.exe gui
```

Pass a file straight to the window:

```powershell
dotdat gui "C:\data\SAMPLE.DAT"
```

The GUI needs the **Microsoft Edge WebView2 runtime**, which ships with Windows
11. `dotdat doctor` reports whether it is present.

---

## Command line quick start

These examples assume the virtualenv is active, so `dotdat` is on the path. In
the built bundle, use `.\dotdat.exe` instead.

```powershell
# Show the header, fields and keys.
dotdat info SAMPLE.DAT

# Show the first 20 rows.
dotdat rows SAMPLE.DAT

# Show 50 rows, only three columns.
dotdat rows SAMPLE.DAT -n 50 --fields ACCOUNT,AREA,BALANCE

# Show matching rows (repeat -w for AND).
dotdat rows SAMPLE.DAT -w "AREA=01" -w "BALANCE>=1000"

# Include deleted rows.
dotdat rows JOURNAL.DAT --include-deleted

# Sort before showing.
dotdat rows SAMPLE.DAT --sort BALANCE --desc -n 25

# Save everything as CSV.
dotdat export SAMPLE.DAT -f csv -o C:\exports\sample.csv

# Save only matching rows and columns.
dotdat export SAMPLE.DAT -f jsonl -w "AREA=01" `
  --fields ACCOUNT,DATE,BALANCE -o C:\exports\area01.jsonl

# List the export formats.
dotdat formats
```

> Field names differ between tables. Run `dotdat info YOURFILE.DAT` to see the
> real names before writing filters.

Useful options:

| Option | Meaning |
|---|---|
| `-n`, `--limit` | Rows to print (default 20, maximum 10,000). |
| `--offset` | Skip matching rows before printing. |
| `-w`, `--where` | Filter; repeat for AND. |
| `--fields` | Comma-separated columns to show or export. |
| `--include-deleted` | Include rows whose deleted bit is set. |
| `--sort`, `--desc` | Sort by a field, optionally descending. |
| `-f`, `--format` | Export format. |
| `-o`, `--output` | Destination file. |
| `--force` | Overwrite an existing export. |
| `-e`, `--encoding` | Text code page (default `cp437`). |

Every command that can fail prints one clear line and a hint, then exits with
code `2`. Tracebacks are not shown to users.

---

## Safety and privacy

- Source files are opened with `rb` and memory-mapped **read-only**. There is no
  write path for `.DAT` files anywhere in the code.
- An export refuses to target the source file, even with `--force`.
- DOTDAT makes no network connections, has no telemetry and uploads nothing.
- Exports may contain customer or financial data. Store and share them with the
  same care as the original tables.
- Corrupt headers fail loudly instead of guessing. A structurally corrupt table
  in the reference set is the deliberate example.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module boundaries and
[docs/FORMAT.md](docs/FORMAT.md) for the on-disk layout.

---

## What it can and cannot read

**Supported:** Clarion 2.x `.DAT` tables with the 85-byte header and fixed-length
records.

**Not supported in v1:**

- TPS, dBase and Clarion 3.x+ tables.
- Editing, deleting, compacting or repairing a table. This is permanent.
- Memo (`.MEM`) bodies.
- Array element details; arrays are shown as raw hex.
- Index-driven jumps. Keys are displayed, but paging follows physical row order.
- Automatic encoding detection. If text looks wrong, try `--encoding cp1252`.

Only LONG, STRING and DECIMAL/BCD field types occur in the reference data. REAL,
PICTURE, BYTE, SHORT and GROUP have best-effort decoders but no real-world
fixture. Sorting materialises every matching row, so it is the one slow path on
the largest table.

---

## Build a standalone Windows exe

Nuitka is not a runtime dependency; install it in the build environment.

```powershell
.venv\Scripts\activate
pip install nuitka
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

The result lands in `build\nuitka\dotdat.dist\`. Keep the whole folder together;
`dotdat.exe` needs the files beside it.

The exe uses the Windows console subsystem so scripts and pipes behave correctly.
For a GUI-only launch it hides its private console window, so double-clicking
still looks like a normal desktop app.

---

## Develop

```powershell
.venv\Scripts\activate
pytest
ruff check src tests benchmarks
mypy src
node --check src\dotdat\ui\web\app.js
```

Real-data tests are skipped unless the reference folder exists:

```powershell
$env:DOTDAT_REFERENCE = "C:\path\to\reference\tables"
pytest -m realdata
```

Without that variable, the suite runs against synthetic tables only. Real tables
are never committed. There are currently 164 tests.

---

## Documentation

- [docs/USAGE.md](docs/USAGE.md) — step-by-step GUI guide, every command and
  troubleshooting
- [docs/CLAVIEW.md](docs/CLAVIEW.md) — how DOTDAT compares with Clarion Viewer,
  feature by feature
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — modules, data flow and gates
- [docs/FORMAT.md](docs/FORMAT.md) — the Clarion 2.x DAT layout
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — plain-language definitions
- [docs/PLAN.md](docs/PLAN.md) — what shipped in v1 and what comes next
- [AGENTS.md](AGENTS.md) — working rules for contributors and agents
- [CONTRIBUTING.md](CONTRIBUTING.md) — development workflow
- [CHANGELOG.md](CHANGELOG.md) — release history
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — dependencies and license notes

---

## License

MIT. See [LICENSE](LICENSE). Clarion is a trademark of its respective owner.
DOTDAT is not affiliated with or endorsed by Clarion or Scalabium Software.
