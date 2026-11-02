# Plan

## Goal

Give anyone holding an old Clarion 2.x database a safe way to look inside and get
the data out, on a modern Windows machine, without installing Clarion and without
risking the original files.

Success means: open every table in the reference set, show correct structure
and values, export every supported format, and never modify a source byte.

## Origin

DOTDAT is a **copy version of Scalabium Clarion Viewer's** read-only browser.
The plan was to reproduce the reference program feature for feature: the same
four views (General Information, Table Structure, Data Grid, Keys), the same
field formatting, the same key listing and the same date handling. The
reference application was reverse engineered as a black box — run on real
tables, observed, timed — and never decompiled. New Python code implements the
observed behaviour; no Clarion Viewer code, assets, help text, icons, language
packs or registration logic is used. The side-by-side record is
[CLAVIEW.md](CLAVIEW.md).

In short: DOTDAT copies the Clarion Viewer experience, not the program.

## v1 scope

| Area | Decision |
|---|---|
| Format | Clarion 2.x `.DAT` only (85-byte header, BCD decimals) |
| Access | Read-only; mmap; no repair or write path |
| Front ends | Typer/Rich CLI and pywebview desktop GUI |
| Exports | CSV, TXT, JSON, JSONL, HTML, XML, SQL, XLSX |
| Platform | Windows 11 first; Python 3.11+ |
| Packaging | Nuitka standalone folder |
| Language | English only |
| Dependencies | Standard library for parsing; openpyxl for XLSX; pywebview for GUI |

Out of scope for v1: TPS, dBase, Clarion 3.x+, memo bodies, index-driven lookup,
record editing, translations, cloud sync.

## Milestones

### 1. Understand the format - done

- Compare candidate structures against the DBF exports that ship beside the tables.
- Confirm the header size, field descriptor size, key layout and record header.
- Confirm BCD sign handling against known balances.
- Confirm the deleted flag against a table with known deleted rows.
- Confirm a structurally corrupt table is rejected, and define the failure message.

Evidence:

- The first record of the largest table decodes to the same values as its DBF
  export: account number, area, day count, amount and balance all match.
- Every table in the reference set parses; one structurally corrupt file is
  rejected cleanly.
- Deleted rows match the header count and the status bit on every record.
- A header claiming an implausible field count was rejected before any record
  was read.

### 2. Engine - done

- `codec.py`: LONG, REAL, STRING, PICTURE, BYTE, SHORT, DECIMAL/BCD, date, time.
- `datfile.py`: validate, parse, mmap, read, page, sort, count, info.
- `query.py`: parse and compile filters.
- `models.py`: immutable structures and JSON shapes.
- `errors.py`: message + hint contract.

### 3. Exports - done

- Eight streaming writers.
- Atomic temp file and rename.
- Cancellation check per row.
- Source-file collision refusal.
- Excel row-cap check.
- Progress callback every 1,000 rows.

### 4. CLI - done

- `info`, `rows`, `export`, `formats`, `gui`, `doctor`, `version`.
- Rich tables and JSON modes.
- Exit code 2 with one-line errors and hints.
- Frozen no-argument launch goes to the GUI.

### 5. GUI - done

- Overview cards and header table.
- Structure and keys.
- Paged data grid with filters, deleted toggle, page size, sorting and jump.
- Export dialog, progress state and cancel.
- Dark retro/matrix styling with no external assets.
- Positionally stable bridge.

### 6. Verification - done

- Synthetic DAT builder and over 150 tests.
- Real-data suite gated on `DOTDAT_REFERENCE`.
- `ruff`, `mypy --strict`, `node --check`.
- Export smoke tests for every format.

### 7. Packaging - done

- `build/launcher.py` absolute-import entry point.
- `build/build.ps1` produces `build\nuitka\dotdat.dist\dotdat.exe`.
- Console subsystem so shells wait, pipes work and exit codes are reliable;
  `build/launcher.py` hides the private console for GUI-only launches.
- Verified the final exe: PE subsystem `3` (console), `doctor` exit 0,
  a corrupt table exits 2, no temp leftovers, and all eight formats valid.

### 8. Documentation and final verification - done

- `README.md` and `docs/USAGE.md` rewritten for first-time users: open a table,
  browse, filter, export, and troubleshoot in plain language.
- Technical detail stays in `docs/FORMAT.md` and `docs/ARCHITECTURE.md`.
- Frozen startup, console hiding and no-argument routing documented in
  `AGENTS.md`, `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`.
- Final source gates: 164 tests, `ruff`, `mypy` and `node --check` pass.
- Built exe smoke-tested for CLI waits, exit codes, all eight exports and the
  GUI (including double-click and console hiding).
- All 37 reference-table SHA256 hashes identical before and after.

### 9. Clarion Viewer parity - done

- Captured the reference's four views and compared them with DOTDAT tab by tab.
- Added the `format` column, the fields and types used by each key, and the
  `0x0030` key type to the Structure tab and `dotdat info`.
- Added date detection and the **dates** toggle; exports keep raw day counts.
- Recorded the comparison, evidence and deliberate differences in
  `docs/CLAVIEW.md`.
- Automated GUI parity checks cover the structure headers, key names, date
  rendering, tooltip and paging.

## Acceptance checklist

- [x] Double-click exe opens the GUI.
- [x] CLI works from the same exe, and shells wait for it.
- [x] All 37 reference tables open except the intentionally corrupt one.
- [x] Corrupt file fails with a clear message, not a traceback.
- [x] Deleted rows hidden by default and countable.
- [x] Filters work on numbers, text and contains.
- [x] Sorting works ascending and descending.
- [x] All eight exports produce valid files.
- [x] A cancelled export leaves no output.
- [x] Source files are unchanged after viewing and exporting.
- [x] Behaviour matches Clarion Viewer for the four views (see `docs/CLAVIEW.md`).
- [x] No Clarion Viewer code, assets or branding is present.
- [x] Docs cover usage, architecture, format and decisions.
- [x] Beginner instructions cover open, browse, filter and export.
- [x] All 37 source hashes are unchanged after the full test pass.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Misreading a field offset damages trust | Validate every offset before reading; compare against DBF ground truth |
| Huge table freezes the UI | mmap, paging, background bridge calls, stale-request guard |
| Sorting 1.4M rows exhausts memory | Document the cost; materialize only on explicit sort |
| Export half-written on crash | temp file + `os.replace`, unlink on exception |
| Excel row limit | pre-flight check when the count is known; clean abort otherwise |
| Unknown legacy field types | best-effort decoders, raw bytes for arrays, explicit limitations |
| Accidental writes | read-only open, no write API, source-path refusal, no edit controls |
| WebView2 missing | `doctor` check and README troubleshooting |

## Next

Ordered by value, not committed to a release:

1. **Streamed GUI export progress.** Report row counts and a percentage instead
   of a coarse status line.
2. **Index-aware paging.** Use key definitions to jump without sorting.
3. **Memo (`.MEM`) viewer.** Read the memo block referenced by each record.
4. **Clarion 3.x / TPS research.** Only with real fixtures and a clean-room
   description; do not link Clarion runtime DLLs.
5. **Field-type fixtures.** Find legitimate samples for REAL, PICTURE, BYTE,
   SHORT and GROUP so their decoders can be verified.
6. **Saved filter presets.** Per-table views in the GUI, stored outside the data
   folder.
7. **Installer.** Inno Setup wrapper around the Nuitka folder, with an optional
   file association.
8. **More encodings.** Auto-detect CP437 vs Windows-1252 with a manual override.

Anything that writes to a `.DAT` stays out, permanently.

## Definition of done

A change is done when:

- the synthetic tests cover the new behaviour;
- the real-data suite still passes (when available);
- `ruff`, `mypy` and `node --check` pass;
- user-facing strings are clear and English;
- docs and `AGENTS.md` invariants are updated if behaviour changed;
- no source table was modified.
