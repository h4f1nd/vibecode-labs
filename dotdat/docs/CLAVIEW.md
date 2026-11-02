# DOTDAT compared with Clarion Viewer

DOTDAT is a **copy version** of the read-only table browser in Scalabium's
**Clarion Viewer**. “Copy” here means a feature-for-feature reimplementation:
the same four views, the same facts, the same value formatting and the same
date handling. It is not a byte copy, and it contains none of the original
program's code, assets, help text, icons, language packs, serial/nag logic or
decompiled output.

The copy was produced by **reverse engineering the original application as a
black box**: opening real tables, switching tabs, reading what the program
displayed and timing what it did, then writing a new Python implementation that
reproduces that behaviour. This document records the plan, what matches, what
is deliberately different, and where the evidence came from.

## What “copy version” means

The project goal was never “write any DAT viewer”. The goal was: **make DOTDAT
behave like Clarion Viewer for the parts that matter to someone reading an old
table**, without shipping anything from Clarion Viewer itself.

| Aspect | Decision |
|---|---|
| Behaviour | Copied: same tabs, columns, values, formatting, date display, key listing |
| Code | New: Python reader, exporters, CLI and GUI written from scratch |
| Assets | None taken: no icons, fonts, help text, language packs or branding |
| Method | Black-box observation of `CLAVIEW.exe` on the 37 reference tables |
| Legal position | Independent, unofficial, MIT-licensed; trademarks used only to describe compatibility |
| Scope | Read-only viewing and exporting of Clarion 2.x `.DAT`; no editing anywhere |

In short: **DOTDAT copies the Clarion Viewer experience, not the Clarion Viewer
program.**

## How the copy was made

1. **Reference.** `CLAVIEW.exe` (Clarion Viewer 3.0, Scalabium Software; the
   `claview` build used for this project) was run on a local reference set of
   legacy tables, starting with a large one (over a million rows). The tables
   are not committed; only the measurements are recorded here.
2. **Observation.** The four tabs were visited and captured: General
   Information, Table Structure, Data Grid and Keys. For each one we recorded
   the columns, the field formatting, the key listing, the date rendering, the
   trial limits and how long the load took.
3. **Measurement.** That table took **roughly nine minutes** to load in the
   trial, and its grid stopped at **100 records**.
4. **Format research.** The `.DAT` byte layout was derived separately from the
   files themselves and from the DBF ground-truth exports beside them. Clarion
   Viewer was a display oracle at this stage, not a source of implementation
   detail.
5. **Reimplementation.** The engine (`mmap` reader, value codecs, filter
   compiler), the exporters, the CLI and the pywebview GUI were written as new
   code with no Clarion runtime or Clarion library.
6. **Parity check.** Each view was compared side by side, then pinned with
   programmatic checks: field list and `format` column, key names and component
   fields, `0x0030` key type, `DATE` shown as `2003-05-26` while `TIME` stays
   a plain number, paging, toggle and export behaviour.

## Same features as Clarion Viewer

The four Clarion Viewer views map onto DOTDAT's three tabs. Nothing from the
reference is missing; two views (structure and keys) share one tab in DOTDAT,
in the same order as the original.

| Clarion Viewer view | DOTDAT tab | Parity |
|---|---|---|
| General Information | **Overview** | Same header facts, plus active/deleted cards and the encoding label |
| Table Structure | **Structure** (fields) | Same field rows, types, offsets and `format` column |
| Data Grid | **Data** | Same columns and values, same date behaviour, full table instead of 100 rows |
| Keys | **Structure** (keys) | Same key names, component fields and types, plus the key type in hex |

Shared beyond the four views:

- a `.DAT` opens directly; there is no import, conversion or database server;
- the source is read-only, with no edit, delete, compact or repair controls;
- the header facts match: record, field and key counts, record length, data
  offset, prefixes and last-change time;
- Clarion type names appear in capitals with byte-accurate offsets and lengths;
- packed BCD numbers and code-page text decode to the same values;
- deleted rows are hidden by default and their count is available;
- day-count columns are presented as calendar dates;
- key definitions list their component fields and types;
- both are Windows desktop programs and need no Clarion runtime to run.

### General Information and Overview

Both answer “what is this file?”. The shared facts are:

- file name and path, file size;
- record count, field count, key count;
- record length, data offset, file prefix and record name;
- signature and attribute bits;
- last-change date and time;
- table encoding.

DOTDAT presents them as summary cards (`records`, `active`, `deleted`,
`fields`, `keys`, `record`) and a key/value table. The reference showed the same
header information; DOTDAT adds the active/deleted split and the encoding label.

### Table Structure and Structure

Both list one row per field with:

| Column | Example | Meaning |
|---|---|---|
| `#` | `1` | Field number used by keys and filters |
| `name` | `ACCOUNT` | Display name, prefix stripped |
| `type` | `DECIMAL` | Clarion type in capitals |
| `offset` | `0` | Byte offset inside the record payload |
| `length` | `7` | Bytes stored |
| `format` | `13.0` | Significant digits and decimals (`9.2` for `AMOUNT`) |
| `dec` | `0` | Decimal places |
| `array` | | Array number, when present |

The `format` column is the piece that makes the two programs look alike: the
reference prints `13.0` for `ACCOUNT` and `9.2` for `AMOUNT`, and DOTDAT derives
the same string from the field descriptor. `dotdat info` prints the column too.

### Data Grid and Data

Both show the same column headers in file order and the same decoded values.
They agree on the details that matter:

- **Deleted rows** are not part of the normal view; DOTDAT hides them by default
  and shows them dimmed when **deleted** is ticked.
- **Dates** are day counts in the file (`73928`), but both programs present a
  detected date column as a calendar date; DOTDAT uses `2003-05-26` (the
  reference's own date text may follow the Windows locale).
- **Numbers** come from the same packed BCD bytes. DOTDAT keeps the field's
  declared scale (`2000.00`); Clarion Viewer may trim trailing zeros, which is
  listed under deliberate differences.
- **Field order** follows the physical record, not the keys.

DOTDAT adds controls the trial did not offer: paging, jump-to-record, page size,
filtering, sorting, a deleted toggle, a dates toggle, and export. The raw day
count stays available in the cell tooltip, and exports always write it.

### Keys and Structure

Both list every key with its name, component count and the fields that make it
up, including each field's type. For `SAMPLE.DAT` DOTDAT prints:

```text
ACCOUNT_KEY  3  0x0030  ACCOUNT (DECIMAL), DATE (LONG), TIME (LONG)
DATE_KEY    2  0x0030  DATE (LONG), ACCOUNT (DECIMAL)
```

DOTDAT prints the key type as the factual `0x0030` hex value. Clarion Viewer's
own flag names (`NOCASE`, `OPT`, `DUP`) are not reproduced, because the file
does not store them in a form that can be attributed reliably; guessing them
would be worse than showing the raw value.

## Where DOTDAT goes further

The copy keeps the reference behaviour but removes the trial limits and adds the
tools a real reader needs. These are additions, not replacements.

| Area | Clarion Viewer (trial observed) | DOTDAT |
|---|---|---|
| Rows in the grid | 100 | all rows, paged |
| Large table load | roughly nine minutes | milliseconds |
| Filtering | not available in the trial view | filter box and `-w` |
| Sorting | not available in the trial view | click a header, or `--sort` |
| Jump to row | not available | **go to record** |
| Deleted rows | hidden | toggle, dimmed style |
| Raw vs date display | fixed | **dates** toggle, raw tooltip |
| Exports | not part of the compared views | CSV, TXT, JSON, JSONL, HTML, XML, SQL, XLSX |
| Command line | GUI only | `info`, `rows`, `export`, `formats`, `doctor` |
| Script output | not available | `--json` for `info` and `rows` |
| Encoding | not user-selectable | `cp437`, `cp1252`, `latin-1`, any Python codec |
| Nag / registration | trial reminder | none |
| Error handling | not compared | one-line message with a hint, exit code 2 |

Measured on the same Windows 11 machine. The load-time
difference is not a micro-optimisation: DOTDAT memory-maps the file and reads
only the rows on screen, so opening a table does not depend on its size.

## Deliberate differences

These are choices, not gaps. Each one is visible and documented.

| Topic | Clarion Viewer | DOTDAT | Why |
|---|---|---|---|
| Date text | Human-readable date | ISO `YYYY-MM-DD` | Unambiguous and sortable; same stored number |
| Decimal scale | Trims trailing zeros (`2000`) | Keeps field scale (`2000.00`) | Lossless and faithful to the descriptor |
| Look | Light Windows chrome | Dark retro/matrix theme | Project style; same layout and information |
| Language | Multiple languages | English only | v1 scope |
| Key flags | Shows `NOCASE`/`OPT`/`DUP` | Shows `0x0030` | Flags are not reliably attributable from the file |
| Navigation | Trial cap | Full table, filter and sort | The point of the copy |
| Editing | Read-only | Read-only | Permanent safety rule |

## What was not copied

The clean-room rule is part of the plan and is enforced in review:

- no Clarion Viewer source code or decompiled output;
- no icons, images, fonts, colours or other visual assets;
- no help text, language packs or translations;
- no serial, registration, nag or trial logic;
- no Clarion runtime DLLs or third-party format libraries.

Only behaviour was observed: which facts appear, in which order, with which
formatting. The implementation behind that behaviour is new code covered by the
MIT licence in [LICENSE](../LICENSE). See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for the dependency list and
the trademark statement.

## Limits of the comparison

- The reference was **Clarion Viewer 3.0** running on Windows 11. Other
  versions or builds may differ.
- The comparison used a local reference set; behaviour on other
  Clarion 2.x files is implemented from the format, not from samples.
- Only the four documented views were compared. Dialogs, printing and other
  Clarion Viewer features were not part of the plan.
- The parity claims are about **observable behaviour**. DOTDAT does not claim
  binary compatibility, nor that it reproduces internal algorithms.

## Independence and trademarks

DOTDAT is unofficial and is not affiliated with or endorsed by Clarion or
Scalabium Software. “Clarion” is a trademark of its respective owner; “Clarion
Viewer” is a product of Scalabium Software. The names are used only to describe
what DOTDAT can read and which behaviour it copies. DOTDAT ships no part of
Clarion Viewer and requires no Clarion licence to run.

## Reproducing the comparison

1. Build or run DOTDAT (see [README](../README.md#run-dotdat)).
2. Open the same table in both programs, for example `SAMPLE.DAT`.
3. Compare the four views: header facts, field list and `format`, grid values
   and dates, key names and component fields.
4. Run `dotdat info SAMPLE.DAT` and compare the printed tables with the GUI.
5. The development workflow also runs GUI parity and smoke checks for the
   structure headers, key names, date rendering, tooltip and paging.

No screenshots are stored in this repository; the numbers and column sets above
are the record of the comparison.
