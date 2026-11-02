# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Because output bytes are the product, a change to any dither kernel or packing
rule is a **breaking** change even if the API looks the same.

## [Unreleased]

### Added

- `--render-width native|8–8192` for PNG/BMP: renders the bitmap at the source
  image's pixel width (or an explicit width) before dithering, producing a clean
  full-resolution logo/header asset instead of a magnified print grid. Rejected
  for ESC/POS and text; sidecars mark it `"screen_export": true`.
- `header` preset (`mean`/Otsu, neutral tone, no dither texture) for logos and
  text. The GUI's **render** selector gains `print`, `native` and fixed widths,
  and the preset chooses `native` when selected there.

## [1.0.0] — 2026-10-27

First release. Conversion only: the app produces 1-bit dot files and never talks
to a printer.

### Added

- Conversion pipeline: decode → fit → tone → dither → `ink` bitmap.
- Paper profiles: 58 mm (384 dots) and 80 mm (576 dots) at 203 dpi, plus custom
  widths from 8 to 2048 dots.
- Seven dither modes: `bayer4` (default), `bayer8`, `atkinson`, `fs`,
  `halftone`, `mean` (Otsu auto-threshold) and `none`.
- Tone controls: gamma, brightness, contrast, invert, auto or fixed threshold.
- Geometry controls: `fit`, `fill`, `stretch`, rotation in 90° steps, margins,
  1-dot border, height cap.
- Four export formats: 1-bit PNG, 1-bit BMP, raw ESC/POS (`GS v 0`), and Unicode
  half-block text; each with an optional JSON sidecar.
- `--upscale 1`–`16` (or `auto`) for PNG/BMP: repeats every dot to produce a
  larger, HD-sized raster with an identical dot pattern. Never applied to
  ESC/POS or text.
- ESC/POS framing options: initialise, feed lines, full cut; tall images split
  into 960-row blocks for firmware safety.
- Atomic writes that report a locked destination as a clear, actionable error.
- Five presets: `hacker-bayer`, `photo-floyd`, `newsprint`, `line-art`,
  `wide-hacker`; explicit flags always override a preset.
- CLI with `convert`, `batch`, `preview`, `presets`, `doctor`, `info` and `gui`,
  with identical geometry and tone options across `convert`, `batch` and
  `preview`.
- Desktop GUI (pywebview + WebView2): drag and drop up to 8 images, live preview
  rendered from the real bitmap, dither hotkeys, presets, paper simulation.
- Prepared-image cache keyed by geometry, so tone and dither changes do not
  re-decode the source.
- Packaging: wheel with bundled web assets, Nuitka standalone build script, Inno
  Setup installer script.
- Documentation set: plan, architecture, usage, glossary, contributing guide,
  agent instructions; documented flags and links are enforced by tests.

### Changed

- JPEG sources are decoded at reduced scale with `Image.draft()`, cutting a
  12 MP conversion from ~142 ms to ~31 ms at 58 mm.
- `atkinson` uses a padded Python list, about 25 % faster and bit-identical to
  the previous implementation.
- GUI previews reuse the decoded image per upload handle: about 5 ms per slider
  tick on a 24 MP photo instead of ~54 ms.

### Fixed

- `fill` could leave a one-dot black edge because `Image.crop()` pads
  out-of-bounds areas with black. It now uses `ImageOps.fit`, which returns the
  exact box.
- Reported total time double-counted the `"total"` timing entry.
- The frozen executable crashed at start-up with
  `ImportError: attempted relative import with no known parent package`; the
  build now uses an absolute-import launcher and a predictable `tdots.dist`
  folder name.
- Exporting over a file held open by another application produced a bare
  `PermissionError`; it now explains the cause and how to fix it.
- An out-of-range `--compress-level` or `--columns 0` produced a traceback;
  both are now option errors with exit code 2.
- Double-clicking the standalone executable printed help into an invisible
  console; with no arguments and no console attached it now opens the GUI.

### Known limitations

- Real thermal paper output has not been verified; only the emitted bytes are
  guaranteed.
- Tested only on Windows 11 with Python 3.14 and current Pillow/NumPy releases.
- `atkinson` is 2–3× slower than the other modes (81 / 151 ms for 12 MP at
  58 / 80 mm).
