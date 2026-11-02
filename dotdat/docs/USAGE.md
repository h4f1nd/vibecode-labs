# Usage

DOTDAT shows one Clarion 2.x `.DAT` table at a time. The desktop window and the
command line use the same reader, so filters, deleted rows and exports behave the
same way in both.

Nothing in DOTDAT can change a source table. The only files it writes are the
exports you choose.

DOTDAT is a **functional copy of Clarion Viewer**, rebuilt from the original's
observed behaviour. If you know the reference program, the views will look
familiar; [If you have used Clarion Viewer](#if-you-have-used-clarion-viewer)
maps them one by one.

- [If you have used Clarion Viewer](#if-you-have-used-clarion-viewer)
- [Use the desktop app (easiest)](#use-the-desktop-app-easiest)
- [Command line](#command-line)
- [Filter language](#filter-language)
- [Export formats](#export-formats)
- [Exit codes and errors](#exit-codes-and-errors)
- [Troubleshooting](#troubleshooting)

---

## If you have used Clarion Viewer

DOTDAT copies the Clarion Viewer workflow on purpose. The views line up:

| Clarion Viewer | DOTDAT |
|---|---|
| General Information | **Overview** |
| Table Structure | **Structure**, field table |
| Data Grid | **Data** |
| Keys | **Structure**, key table |

The facts and formatting are the same: field names and types, the `format`
column (`13.0`, `9.2`), key names with their component fields and field types,
the `0x0030` key type, and a date column such as `DATE` shown as
`2003-05-26` rather than `73928`.

What changes is the trial limits. DOTDAT shows the whole table instead of 100
rows, opens it in milliseconds instead of minutes, and adds filtering, sorting,
jumping, deleted and dates toggles, and export. The stored values are unchanged:
the **dates** toggle, filters and every export use the raw day count.

The full feature-by-feature comparison is in [CLAVIEW.md](CLAVIEW.md).

---

## Use the desktop app (easiest)

### Open a table

1. Start DOTDAT:
   - double-click `build\nuitka\dotdat.dist\dotdat.exe`, or
   - run `dotdat.exe gui`, or
   - run `dotdat gui` from an activated virtualenv.
2. Click **Open .DAT**.
3. Choose a `.DAT` file. The dialog starts with `.DAT` files, but **All files**
   is available too.
4. The window fills in. Click **Data** to see the rows.

You can skip step 2 by passing the file on the command line:

```powershell
dotdat.exe gui "C:\data\SAMPLE.DAT"
```

The **encoding** dropdown controls how text bytes are turned into letters. The
default `cp437` is correct for the reference tables. Changing the dropdown does
not reload the current table; it applies the next time you open a file.

### The three tabs

**Overview** answers “what is this file?” It shows cards for total rows, active
rows, deleted rows, fields, keys and record length, then a table with the
signature, attributes, offsets, names, last-change time and encoding.

**Structure** answers “what columns does it have?” Fields are listed with their
index, display name, type, offset, length, `format` (the significant digits and
decimals, such as `13.0` or `9.2`), decimals and array number. Keys follow with
the fields that make them up, for example `ACCOUNT (DECIMAL), DATE (LONG)`, plus
the key type in hex. Use this tab to copy an exact field name for a filter.

**Data** is the working view:

- **filter** — type an expression and press **Enter**. DOTDAT also applies it
  automatically after a short pause. Press **Escape** to clear it.
- **deleted** — tick to include rows whose deleted bit is set. They appear with a
  dimmed style. Unticked is the safe default.
- **dates** — ticked by default. A Clarion date is really a whole number of days
  since 28 December 1800, so DOTDAT shows such a column as `2003-05-26` instead
  of `73928`. Hover a cell to see the stored number. Untick **dates** to see the
  raw numbers everywhere. Exports always keep the raw numbers.
- **rows** — 50, 100, 500 or 1000 rows per page. Changing it returns to the
  first page.
- **‹ prev / next ›** — move through matching rows.
- **go to record** — jump to a one-based row number. DOTDAT moves to the page
  that contains that row, so the page can start a little earlier. With a filter
  or hidden deleted rows, the number refers to the matching list, not the
  physical file, so it is most useful on an unfiltered table.
- **column headers** — click once to sort ascending, again for descending, a third
  time to return to file order.
- **Export** — choose a format, then a destination.

A sort on a table with over a million rows can take seconds. The status bar shows
that work is in progress. A filter scan on the largest reference table takes
roughly 15–25 seconds; paging is instant because only the visible rows are read.

### Save what you see

1. Apply a filter and choose whether deleted rows are included.
2. Pick a format in the dropdown next to **Export**.
3. Click **Export**.
4. Choose a folder and file name in the save dialog.

The export contains **all matching rows**, not just the current page. It respects
the filter, the deleted checkbox and the current sort. The GUI exports all
columns; use the CLI's `--fields` option when you need a subset.

If the destination exists, the operating system's save dialog asks before
replacing it. During a long export, **Cancel** stops at the next row and removes
the partial file. A successful export shows a toast with the row count and path.

### Close safely

Closing the window while idle only releases the read-only file mapping. Your
source file is untouched.

Use **Cancel** to stop a running export: it stops at the next row and removes the
temporary file. Closing the whole window during an export exits the process
immediately, so a hidden `.<name>.<pid>.tmp` file may remain in the destination
folder. It is safe to delete, and the source table is still untouched.

---

## Command line

Run `dotdat` from an activated virtualenv, or call
`.venv\Scripts\dotdat.exe`. In the built bundle use `.\dotdat.exe` from the
`build\nuitka\dotdat.dist` folder.

The exe uses the console subsystem, so PowerShell and `cmd.exe` wait for it,
pipes work and `$LASTEXITCODE` / `%ERRORLEVEL%` is reliable.

### `dotdat info`

Show the 85-byte header plus the field and key tables.

```powershell
dotdat info SAMPLE.DAT
dotdat info SAMPLE.DAT --json
dotdat info SAMPLE.DAT --encoding cp1252
```

`--json` emits one object with `path`, `file_name`, `size`, `encoding`, `header`,
`fields` and `keys`, plus `last_change` and `date_fields` (the LONG columns the
GUI will show as dates). Use it for scripts; the text view is for humans.

### `dotdat rows`

Print a page of decoded rows.

```powershell
dotdat rows SAMPLE.DAT
dotdat rows SAMPLE.DAT -n 50 --offset 1000
dotdat rows SAMPLE.DAT --fields ACCOUNT,AREA,BALANCE
dotdat rows SAMPLE.DAT -w "YEAR=2026"
dotdat rows SAMPLE.DAT -w "BALANCE>=1000" -w "AREA=01"
dotdat rows SAMPLE.DAT --include-deleted
dotdat rows SAMPLE.DAT --sort BALANCE --desc
dotdat rows SAMPLE.DAT --json
```

| Option | Default | Meaning |
|---|---|---|
| `-n`, `--limit` | `20` | Rows per page, 1–10,000 |
| `--offset` | `0` | Matching-row offset |
| `-w`, `--where` | none | Filter expression; repeat for AND |
| `--fields` | all | Comma-separated display names |
| `--include-deleted` | off | Show rows with `status & 0x10` |
| `--sort` | file order | Field to sort by |
| `--desc` | off | Descending sort |
| `-e`, `--encoding` | `cp437` | String code page |
| `--json` | off | Machine-readable page |

`--json` returns `offset`, `limit`, `total` (or `null` when filtered/sorted),
`has_more`, and rows with `record`, `status`, `deleted` and `values`.

### `dotdat export`

Stream every matching row to a file.

```powershell
dotdat export SAMPLE.DAT
dotdat export SAMPLE.DAT -f csv -o C:\exports\sample.csv
dotdat export SAMPLE.DAT -f jsonl -w "AREA=01" --fields ACCOUNT,BALANCE
dotdat export JOURNAL.DAT -f xlsx --include-deleted -o C:\exports\journal.xlsx
dotdat export SAMPLE.DAT -f sql --sort ACCOUNT -o C:\exports\sample.sql
```

| Option | Default | Meaning |
|---|---|---|
| `-f`, `--format` | `csv` | One of the eight formats |
| `-o`, `--output` | source name + extension | Destination path |
| `-w`, `--where` | none | Filter; repeat for AND |
| `--fields` | all | Comma-separated display names |
| `--include-deleted` | off | Include deleted rows |
| `--sort` / `--desc` | file order / off | Sort before writing |
| `-e`, `--encoding` | `cp437` | String code page |
| `--force` | off | Overwrite an existing destination |
| `-q`, `--quiet` | off | No progress or summary |

There is no `--limit`: an export writes all matching rows. Use a filter to bound
it. A default output name sits beside the source; pass `-o` to keep exports away
from production data.

Exports are atomic. The writer creates a hidden temporary file in the destination
folder and renames it only after the last row. A failure or Ctrl+C leaves no
partial output.

### `dotdat formats`

```powershell
dotdat formats
```

Lists each format and its extension.

### `dotdat gui`

```powershell
dotdat gui
dotdat gui SAMPLE.DAT
dotdat gui SAMPLE.DAT --encoding cp1252
```

Opens the desktop window, optionally with a file already loaded. The encoding is
remembered for that window; changing the dropdown applies the next time a file is
opened.

### `dotdat doctor`

Reports the version, Python, executable, whether `openpyxl`, `pywebview` and
`tkinter` are importable, and the Edge WebView2 runtime version on Windows.
`tkinter` is informational only; DOTDAT does not use it.

### `dotdat version`

Prints the version and exits.

---

## Filter language

Expressions are ANDed. In the CLI repeat `--where`; in the GUI separate them with
`;`.

| Operator | Meaning | Example |
|---|---|---|
| `=` | equals | `AREA=01` |
| `!=`, `<>` | not equals | `CODE!=9` |
| `>` | greater than | `BALANCE>1000` |
| `>=` | greater or equal | `DATE>=73000` |
| `<` | less than | `BALANCE<0` |
| `<=` | less or equal | `YEAR<=2025` |
| `~` | contains, case-insensitive | `NAME~sample` |
| `~=` | contains, same as `~` | `NAME~=sample` |
| `contains` | contains, same as `~` | `NAME contains sample` |

Rules:

- Field names are case-insensitive. The stored prefix is optional:
  `ACCOUNT` and `SMP:ACCOUNT` both work.
- LONG, BYTE, SHORT and DECIMAL fields compare numerically. STRING fields
  compare case-insensitively.
- Quote values with spaces: `NAME="SAMPLE CUSTOMER"`.
- `~` works on numbers too because it compares the rendered text (`ACCOUNT~2010`).
- An empty value is allowed only for `=`, `!=` and `<>`.
- Unknown fields and unparseable expressions fail before any row is read.
- There is no OR. Use two exports or a contains expression when one condition
  cannot express what you need.

**Dates and times are raw Clarion values.** A date is a day count from
1800-12-28 (for example `73928`), not `YYYYMMDD`. A time is centiseconds since
midnight, not `HH:MM`. The GUI can show a detected date column as `2003-05-26`,
but filters, the `rows` command and every export always compare and write the
raw number, so use `DATE>=82214` rather than `DATE>=2005-01-01`. Look at a
few rows before filtering on them.

The GUI shows the total as **unknown (filtered)** when a filter or sort is active,
because counting would require a full second scan. The rows you can see are still
correct.

---

## Export formats

| Format | Extension | Shape |
|---|---|---|
| CSV | `.csv` | UTF-8, comma separated, header row |
| TXT | `.txt` | UTF-8, tab separated, header row |
| JSON | `.json` | one array of objects |
| JSONL | `.jsonl` | one object per line |
| HTML | `.html` | standalone table, sticky header |
| XML | `.xml` | `<table>` → `<record>` → `<field name="…">` |
| SQL | `.sql` | `CREATE TABLE` plus batched `INSERT` |
| XLSX | `.xlsx` | one write-only worksheet |

Value rules:

- DECIMAL values are written as exact decimal strings in JSON/JSONL, as exact
  decimal text in CSV/TXT/HTML/XML/SQL, and as floats in XLSX.
- BYTE arrays and unknown types are written as hex.
- The `status` and `deleted` columns are not added to exports; use
  `--include-deleted` to include those rows. Deleted rows are otherwise omitted.
- SQL identifiers are double-quoted; single quotes in values are doubled. The
  table name comes from the table header (for example `RECORD`).
- Excel is limited to 1,048,576 rows including the header. DOTDAT refuses an
  unfiltered XLSX export that cannot fit, and stops a filtered one cleanly if
  the scan crosses the limit.
- Line endings are `\n`, even on Windows. Excel and every modern editor accept
  them.

If you need only some columns, use the CLI:

```powershell
dotdat export SAMPLE.DAT -f csv --fields ACCOUNT,BALANCE -o C:\exports\small.csv
```

---

## Exit codes and errors

| Code | Meaning |
|---|---|
| `0` | success |
| `2` | expected error, invalid usage, corrupt/unsupported file, export refusal |
| other | unexpected interpreter failure (please report it) |

Expected errors print one line and a hint. Tracebacks are disabled in the CLI.
Examples:

```text
error SAMPLE.DAT declares an implausible number of fields.
hint  The header is damaged. Restore the file from a backup.
```

```text
error C:\out.csv already exists.
hint  Pass --force to overwrite it, or choose another path.
```

The GUI shows the same message and hint in a toast and leaves the table open.

---

## Troubleshooting

**Windows warns about an unknown publisher.**
The exe is not code-signed. If you built it yourself, choose **More info → Run
anyway**. Do not bypass the warning for a copy you did not build or download from
a source you trust.

**Double-clicking shows a console window for a moment.**
The exe is a console program so CLI piping and exit codes work. When launched
from Explorer it hides its private console as soon as the window starts. A brief
flash is normal.

**"The GUI needs pywebview."**
Install the GUI extra: `pip install "dotdat[gui]"`. In the built bundle this
should be included; rebuild if it is missing.

**Blank window or no WebView2.**
Install the Microsoft Edge WebView2 runtime (preinstalled on Windows 11), or run
`dotdat doctor` to confirm what is available.

**The text looks like `Ã©` or `?`.**
The code page is wrong. Reopen the file with `--encoding cp1252` or another
code page. The reference tables use `cp437`.

**"not a Clarion 2.x DAT file".**
The file is TPS, dBase, text, or a Clarion 3.x+ table. DOTDAT v1 only reads the
Clarion 2.x layout described in [FORMAT.md](FORMAT.md).

**"declares N fields; that is not plausible."**
The header is damaged. DOTDAT refuses to guess. Restore from backup; do not run a
repair tool against the only copy.

**"declares N records but is only M bytes".**
The file is truncated. Restore the missing tail.

**Excel export refuses.**
The table or filter result exceeds 1,048,576 rows. Use CSV, JSONL or SQL, which
stream without a row cap.

**Sorting takes a long time.**
Sorting materialises every matching row. Add a filter, or export in file order
and sort downstream.

**Filter finds nothing.**
Check the schema with `dotdat info`. Remember string comparisons are
case-insensitive but do not ignore punctuation; dates are Clarion day counts, not
ISO strings. Also check whether the rows you want are marked deleted.

**Dates look like five-digit numbers.**
That is how Clarion stores them: a day count from 1800-12-28. DOTDAT shows a
detected date column as `2003-05-26`, and unticking **dates** shows the stored
number again. Exports always keep the number so nothing is lost; convert with the
Clarion epoch in your spreadsheet or script if you need calendar dates there.

**"Cannot write … Access is denied".**
Choose another folder, close the file in Excel or another program, or check free
space. DOTDAT never overwrites without permission.

**An export finished but the file is empty.**
The filter matched no rows, or the only matches were deleted and **deleted** was
unticked. Clear the filter and check the toggle.
