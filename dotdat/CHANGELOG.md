# Changelog

All notable changes to DOTDAT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The Structure tab shows a `format` column (`13.0`, `9.2`) and keys now list
  the fields and types they use (`ACCOUNT (DECIMAL), DATE (LONG)`) plus the key
  type in hex, matching what Clarion's own viewer shows. `dotdat info` prints the
  same columns.
- The Data tab recognises Clarion date columns and shows them as `YYYY-MM-DD`;
  a new **dates** checkbox switches back to raw day counts, and every export
  still writes the stored number.
- `info --json` reports `date_fields`.

### Fixed

- The standalone exe now uses the Windows console subsystem. PowerShell and
  `cmd.exe` wait for CLI commands, pipes are complete, and exit codes are
  reliable. Previously the GUI-subsystem exe returned immediately.
- Double-clicking `dotdat.exe` (or running it with no arguments) opens the GUI
  again. Nuitka does not set `sys.frozen`, so the launcher now routes an
  argument-free start to `gui` explicitly.
- A GUI launch from Explorer hides its private console window; a launch from a
  terminal leaves the shared console alone.

### Changed

- `README.md` and `docs/USAGE.md` were rewritten for first-time users:
  open, look, filter and export in plain language, with the technical detail
  moved to `docs/FORMAT.md` and `docs/ARCHITECTURE.md`.
- Documentation now records the frozen startup behaviour and the console
  subsystem requirement.

### Documentation

- Added `docs/CLAVIEW.md`, a feature-by-feature comparison with Clarion Viewer,
  the reverse-engineering method, evidence and the deliberate differences.
- All user and maintainer docs now state that DOTDAT is a functional copy of
  Clarion Viewer's read-only browser, built by black-box reverse engineering.
  The parity record is linked from the README, usage, format, architecture,
  plan, glossary, contributor and agent docs.

### Verified

- Over 150 tests pass, along with `ruff`, `mypy` and `node --check`.
- All eight export formats were checked from both the source app and the built
  exe; row counts and decoded values match.
- All 37 reference-table SHA256 hashes are identical before and after viewing,
  filtering and exporting.

## [0.1.0] - 2026-10-27

First release. Read-only Clarion 2.x `.DAT` viewer and exporter.

### Added

- Pure-Python reader for the 85-byte Clarion 2.x header, 27-byte field
  descriptors, variable key blocks and 5-byte record headers.
- Decoders for LONG, STRING, DECIMAL (packed BCD), REAL, PICTURE, BYTE, SHORT,
  GROUP and array placeholders; Clarion date and time conversion.
- Deleted-record detection from `status & 0x10`, with an include-deleted toggle.
- Memory-mapped, read-only access; a 1.4 million row table opens without reading
  the payload.
- Paging, filtering and sorting in the engine shared by the CLI and GUI.
- Filter scans decode only the fields named in the expressions; the full record
  is re-read only for rows that match. A full scan of the largest reference
  table takes 15-25 seconds instead of 80-100.
- Filter language: `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `~`, `~=` and
  `contains`, combined with AND.
- Exports to CSV, TXT, JSON, JSONL, HTML, XML, SQL and XLSX. Every writer is
  atomic and cancellable.
- Typer CLI: `info`, `rows`, `export`, `formats`, `gui`, `doctor`, `version`.
- pywebview desktop GUI with overview cards, header table, structure and keys,
  a paged data grid, filter box, sorting, jump-to-record and export dialog.
- Dark retro/matrix styling; no external assets or icon packs.
- Nuitka standalone build script and frozen entry point.
- Synthetic DAT builder and over 150 tests, including opt-in checks against a
  local reference set.

### Verified

- Every table in the reference set is parsed. A structurally corrupt file is
  rejected cleanly with a message instead of a crash.
- The largest table decodes end to end: header counts, field offsets, key
  definitions and the first record were cross-checked against its DBF export.
- A table with deleted rows confirmed the deleted status bit on every record and
  matched the count reported by the header.
- A corrupt header claiming an implausible field count was rejected before any
  record was read.

### Known limitations

- TPS and dBase tables are out of scope.
- Memo (`.MEM`) content is not decoded.
- Array element descriptors are not available in this format revision; arrays
  render as hex.
- Sorting materializes all matching rows.
- Excel export is capped at 1,048,576 rows including the header.
- GUI export progress is coarse; Cancel stops at the next row.
