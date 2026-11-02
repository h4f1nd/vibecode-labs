# Plan — what `thermal-dots` is, and what it should stay

This is the anchor document for the project. If a future change conflicts with
this file, either the change is wrong or this file needs a deliberate edit —
never a silent drift.

- Applies to: `thermal-dots` 1.0.0
- Audience: the maintainer, future contributors, and AI agents working in this
  repository
- Related: [README](../README.md) (usage) · [ARCHITECTURE](ARCHITECTURE.md)
  (how it works today) · [USAGE](USAGE.md) (every flag) ·
  [GLOSSARY](GLOSSARY.md) (vocabulary)

---

## 1. Summary

`thermal-dots` turns an ordinary image into the dots a thermal receipt printer
can print. The output is exact: 384 dots wide for 58 mm paper, 576 dots wide for
80 mm paper, one bit per dot. It writes those dots to a file (PNG, BMP, raw
ESC/POS or text art) and stops there.

It does not print. Another program owns the connection to the printer.

## 2. The problem

A thermal print head has one job per dot: fire (black) or do not fire (paper).
There is no grey. Everything that makes a photo look good on that hardware is
decided *before* the bytes reach the printer:

1. **Tone.** Cheap thermal paper blooms, so mid-greys need to be biased.
2. **Dithering.** Every grey pixel must become a pattern of black and white dots.
   The choice of pattern is the difference between a recognisable face and mud.
3. **Geometry.** The image must land on an exact dot grid; half a dot of drift
   shows up as a white seam.
4. **Byte layout.** ESC/POS stores eight dots per byte, most significant bit
   first, bit `1` = black. Get the polarity wrong and you print a negative.
5. **Tuning loop.** Nobody can predict the result from numbers alone, so a fast
   preview that uses the *same* code path as the export is part of the feature,
   not a luxury.

The hard part is not printing. It is choosing dots well, repeatably.

## 3. Scope

**In scope**

| Area | What it covers |
|---|---|
| Decode | JPEG, PNG, BMP, GIF, TIFF, WebP and anything else Pillow reads; EXIF rotation; transparency flattened onto white |
| Geometry | Paper width, `fit` / `fill` / `stretch`, rotation, margins, border, height cap |
| Tone | Gamma, brightness, contrast, invert, auto or fixed threshold |
| Dithering | Seven modes (`bayer4`, `bayer8`, `atkinson`, `fs`, `halftone`, `mean`, `none`) |
| Presets | Five named starting points, overridable per flag |
| Export | 1-bit PNG, 1-bit BMP, raw ESC/POS `.bin`, Unicode half-block `.txt`, plus a JSON sidecar; optional nearest-neighbour raster upscale (1-16 or `auto`) for PNG/BMP; optional native render width (source width or 8-8192 px) for clean screen/header assets |
| Front-ends | CLI (`tdots`) and a desktop GUI (pywebview) that share one engine |
| Packaging | Wheel, standalone Windows folder via Nuitka, optional Inno Setup installer |
| Docs | This document set, enforced by `tests/test_docs.py` |

**Out of scope — permanently**

- Sending bytes to a printer (USB, serial, Bluetooth, network, driver spooling)
- Printer discovery, status polling, paper-out handling
- Print queues, scheduling, retries, job history
- Cloud sync, accounts, telemetry, network calls of any kind
- Colour printing, greyscale printing, PDF layout, OCR, AI upscaling
- Image editing beyond the tone/geometry options above

These are exclusions, not "not yet". Adding transport would turn a deterministic
converter into a device-support project, and `docs/PLAN.md` would become a lie.

## 4. Requirements

Requirement IDs are stable. Cite them in commits and tests when relevant.

### 4.1 Functional

| ID | Requirement | Verified by |
|---|---|---|
| F1 | 58 mm output is exactly 384 dots wide | `tests/test_pipeline.py`, `tests/test_exporters.py` |
| F2 | 80 mm output is exactly 576 dots wide | same |
| F3 | Custom widths are accepted from 8 to 2048 dots | `tests/test_pipeline.py` |
| F4 | Seven dither modes exist; default is `bayer4` | `tests/test_dither.py`, `tests/test_golden.py` |
| F5 | Tone controls: gamma 0.1–5.0, brightness −255–255, contrast 0.1–4.0, invert | `tests/test_cli.py`, `tests/test_pipeline.py` |
| F6 | Geometry: `fit`/`fill`/`stretch`, rotate 0/90/180/270, margin, 1-dot border, max height | `tests/test_pipeline.py` |
| F7 | Four export formats plus an optional JSON sidecar | `tests/test_exporters.py` |
| F8 | Six presets exist; an explicit flag always beats the preset | `tests/test_cli.py` |
| F9 | CLI has `convert`, `batch`, `preview`, `presets`, `doctor`, `info`, `gui` | `tests/test_cli.py` |
| F10 | GUI exposes the same engine, previewing through the same `convert()` | `tests/test_ui_api.py` |
| F11 | No option combination can produce a width other than the requested one | `tests/test_pipeline.py` |
| F12 | PNG/BMP may be enlarged by 1–16× (or `auto`); the dots, and all ESC/POS bytes, are unchanged | `tests/test_exporters.py`, `tests/test_cli.py` |
| F13 | `--render-width native` (or an explicit 8–8192 px) renders the bitmap at that width for a clean screen asset; ESC/POS and text refuse it | `tests/test_cli.py`, `tests/test_ui_api.py`, `tests/test_pipeline.py` |
| F14 | The `header` preset plus native rendering produces a 1-bit logo/header with no dither texture | `tests/test_cli.py` |

### 4.2 Non-functional

| ID | Requirement | Number | Verified by |
|---|---|---|---|
| N1 | Deterministic output | Same input + same options ⇒ identical bytes, forever | `tests/test_golden.py` (17 fingerprints) |
| N2 | Conversion speed | ≤ 50 ms for a 12 MP JPEG at 58 mm (median of 5) | `benchmarks/bench.py` |
| N3 | GUI interaction speed | ≤ 10 ms per slider tick on a 24 MP photo after first load | `benchmarks/bench.py`, `tests/test_ui_api.py` |
| N4 | No network access | Zero sockets opened, ever | code review; no HTTP client dependency |
| N5 | Bounded memory | Decoded-image cache holds at most 4 images; sources above 120 MP are rejected | `tests/test_pipeline.py` |
| N6 | Correct row padding | Padding bits in the last byte of a row are always `0` | `tests/test_exporters.py` (independent parser) |
| N7 | No partial output files | Writes are atomic (temp file + replace) | `tests/test_exporters.py` |
| N8 | Clear failure on locked files | `Cannot overwrite <path> …`, exit code 2 | `tests/test_exporters.py`, `tests/test_cli.py` |

## 5. Architecture

One pure pipeline, plus thin adapters for the CLI and the GUI. Full detail lives
in [ARCHITECTURE](ARCHITECTURE.md); the shape is:

```
source (path / bytes / stream / PIL / ndarray)
   │
   ├─ decode   ── Image.open header ─ draft() shrinks JPEG before full decode
   │                └─ size guard: > 120 MP → ImageTooLargeError
   ├─ geometry ── exif_transpose → rotate → grey → fit/fill/stretch → canvas
   ├─ tone     ── 256-entry LUT (gamma, contrast, brightness, invert)
   ├─ dither   ── NumPy kernels → ink: bool[H, W]   (True = fire the head)
   └─ export   ── PNG │ BMP │ ESC/POS │ half-block text  (+ JSON sidecar)
```

`convert()` is a pure function of `(source, ConvertOptions)`. The only shared
state in the package is a 4-entry cache of *prepared* images; it is keyed by
geometry and guarded by a lock. Nothing else mutates between calls.

## 6. Invariants

These are the rules that, if broken, produce a plausible-looking build with
wrong output. Each one names the test that should fail.

| ID | Invariant | Guard |
|---|---|---|
| I1 | The canonical bitmap is `ink: bool[H, W]`, `True` = printed dot | `tests/test_bits.py` |
| I2 | ESC/POS packs MSB-first, bit `1` = dot; Pillow mode `"1"` has bit `1` = **white**, so `ink_to_pil` inverts | `tests/test_bits.py`, `tests/test_exporters.py` |
| I3 | `PIL.Image.tobytes()` is the bitwise **complement** of the ESC/POS payload and must never be written raw | `tests/test_exporters.py` |
| I4 | Row padding bits are blank, at any width | `tests/test_bits.py`, parser round-trip in `tests/test_exporters.py` |
| I5 | Output width equals `options.resolved_width()` exactly, including margins and border | `tests/test_pipeline.py` |
| I6 | The cache key covers geometry only — never dither or tone | `tests/test_pipeline.py`, `tests/test_ui_api.py` |
| I7 | GUI bridge methods stay positionally callable (pywebview passes arguments positionally) | `tests/test_ui_api.py` |
| I8 | Documented flags and links are real | `tests/test_docs.py` |
| I9 | Native render width changes the bitmap before dithering and never reaches ESC/POS or text output | `tests/test_cli.py`, `tests/test_pipeline.py` |

When you intentionally change a dither kernel, regenerate the golden hashes:

```powershell
.venv\Scripts\python -m tests.golden.regen
```

## 7. Decisions and rationale

Short ADR-style records. "Rejected" is the part that saves future time.

| ID | Decision | Why | Rejected |
|---|---|---|---|
| D1 | Python 3.11+ with NumPy + Pillow | Best image decoders and vectorised kernels for free | Pure-C, Rust, JavaScript |
| D2 | Canonical `ink` boolean array | One representation; exporters derive everything | Packed bytes as the model |
| D3 | Pillow for decode/resize, NumPy for dithering | Pillow's decoders and Lanczos are battle-tested; dither maths is simple array work | Doing resize in NumPy |
| D4 | `bayer4` as default | Stable, structured look; hides JPEG noise better than threshold | Floyd–Steinberg default (too noisy on receipts) |
| D5 | Atkinson in a padded Python list | ~25 % faster than the naive version and bit-identical | Rewriting in Cython/Numba (build complexity) |
| D6 | `fill` uses `ImageOps.fit` | Guarantees the exact box; manual crop leaves a gap that prints black | Manual crop + resize |
| D7 | LANCZOS everywhere | Best detail retention when shrinking to 384 dots | BILINEAR, NEAREST |
| D8 | ESC/POS split every 960 rows | Some firmware cannot buffer taller raster commands | One giant `GS v 0` block |
| D9 | Atomic writes via temp file + replace | Never leave a half-written PNG where a print job expects one | Direct `open(..., "wb")` |
| D10 | 4-entry prepared-image cache, geometry-keyed | Slider drags cost ~5 ms instead of a full decode | No cache (slow), full-options key (useless) |
| D11 | pywebview GUI with `private_mode=True` | WebView2 profile caching served a stale `index.html` | Electron (100 MB), Tkinter (no styling) |
| D12 | Typer + Rich | Typed options, good `--help`, readable tables | argparse, Click directly |
| D13 | Nuitka standalone, not PyInstaller | Real compiled output, no bootloader unpacking, smaller AV surface | PyInstaller, zipapp |
| D14 | Docs tested like code | A wrong flag in the README is a bug users hit first | Trusting prose |
| D15 | Raster upscale is nearest-neighbour, after dithering | Bigger PNG/BMP for screens without changing a dot; `auto` matches the source width | Smooth interpolation (invents greys), re-dithering at export size (breaks the print contract) |
| D16 | Native render width samples before dithering and is raster-only | A clean full-resolution logo/header needs real pixels at that width, not repeated print dots; `bin`/`txt` stay printable | Treating native as another upscale (soft/blurred text), allowing it for ESC/POS (a print head cannot use it) |

## 8. Verification strategy

The testing pyramid is used literally: many cheap unit tests, a few expensive
end-to-end checks, and manual checks where automation cannot see.

| Layer | What it proves | Where |
|---|---|---|
| Unit | Each kernel, packer, LUT and error path | `tests/test_bits.py`, `tests/test_dither.py`, `tests/test_pipeline.py` |
| Property | Pack/unpack round-trips at arbitrary widths and heights | `tests/test_bits.py` (Hypothesis) |
| Golden | 17 image/mode/paper combinations never drift silently | `tests/test_golden.py` + `tests/golden/hashes.json` |
| Byte-level | ESC/POS output parses back to the exact `ink` bitmap, including padding | `tests/test_exporters.py` (independent parser, not the packer) |
| Decode corpus | Real-world modes: `RGB`, `RGBA`, `P`, `L`, `I;16`, `CMYK`, EXIF-rotated | `tests/test_modes.py` |
| CLI contract | Flags exist, aliases agree, presets override correctly, exits are 2/1/0 | `tests/test_cli.py` (Typer `CliRunner`) |
| GUI contract | Bridge signatures, error payloads, export paths, `MAX_SOURCES` | `tests/test_ui_api.py` |
| Docs | Every documented flag exists, every link resolves, README tables match the enums | `tests/test_docs.py` |
| Manual | WebView2 actually renders CSS/JS and returns a 384-dot preview | `gui_smoke.py` (outside the repo) |
| Manual, not done | Real paper, real printer, dot bloom | — |

A CI workflow now exists at `.github/workflows/thermal-dots.yml` in the
repository root. It runs the four gates on Windows for Python 3.11 and 3.14 on
every push to `main` and every pull request that touches `thermal-dots/`. The
same gates must pass locally before a change is merged (`pytest`, `ruff`,
`mypy`, `node --check`).

## 9. Performance

Measured with `benchmarks/bench.py` on:

- CPU: 4-core laptop CPU (8 logical threads)
- Windows 11, Python 3.14, current Pillow and NumPy releases
- Input: 4000 × 3000 JPEG (12 MP), default tone, `fit`
- Median of 5 runs per cell, milliseconds end-to-end

| Dither | 58 mm (384) | 80 mm (576) |
|---|---:|---:|
| `bayer4` (default) | 31 | 44 |
| `bayer8` | 32 | 47 |
| `halftone` | 30 | 44 |
| `mean` | 30 | 41 |
| `none` | 30 | 42 |
| `fs` | 32 | 45 |
| `atkinson` | 81 | 151 |

Reproduce:

```powershell
.venv\Scripts\python benchmarks\bench.py --repeat 5
```

Notes:

- `atkinson` is the outlier on purpose: error diffusion is sequential, so it runs
  in a Python loop over the image. Floyd–Steinberg uses Pillow's C implementation;
  every other mode is a NumPy kernel.
- The GUI is faster than these numbers suggest because it caches the prepared
  image: after the first conversion a slider tick is ~5 ms on a 24 MP photo.

## 10. Risks

| Risk | Impact | Mitigation | Status |
|---|---|---|---|
| ESC/POS row limit varies by firmware | Garbled or truncated print on some clones | 960-row fragmentation (D8) | Mitigated, untested on hardware |
| Real paper blooms | Prints look heavier than the PNG preview | Tone controls + presets; documented in USAGE | Documented, unvalidated |
| Nuitka build breaks on upgrade | No standalone binary | Build script is one command; launcher is 10 lines | Was broken once (relative import); fixed and smoke-tested |
| WebView2 missing | GUI cannot start | `tdots doctor` reports it; CLI still works | Handled |
| Windows-only assumptions | No macOS/Linux GUI path | `doctor` and errors stay honest; CLI is portable | Accepted for 1.0 |
| Docs drift from code | Users copy flags that do not exist | `tests/test_docs.py` | Enforced |
| CI not yet green in practice | Regressions reach `main` | Root workflow runs the same four gates; local gates documented in CONTRIBUTING | Watched on first push |

## 11. Roadmap

**Now (1.0.0)**

- Conversion engine, CLI, GUI, exports, presets — done
- Native-resolution header/logo export (`--render-width`, `header` preset) — done, unreleased
- Documentation set — done
- CI workflow (Windows, Python 3.11 + 3.14) — in the repository root, scoped to
  this folder by `paths:`

**Next (1.1)**

- Screenshots and sample outputs in `docs/images/`
- Compile and test `build\installer.iss`; publish the standalone bundle with the release
- GitHub repository metadata (`[project.urls]`, issue templates already in place)

**Later**

- Additional dither kernels (Stucki, Sierra) if a real use case appears
- HEIF support via the optional `heif` extra, documented and tested
- Linux/macOS packaging notes (engine is already portable)

**Not planned**

- Printing, transport, device discovery — see §3
- Colour output, PDF layout, batch scheduling, cloud features

## 12. Status

What has actually been run, as opposed to written down.

| Claim | Evidence | Date |
|---|---|---|
| 221 tests pass (3 skipped) | `pytest -q` | 2026-10-27 |
| Lint and types clean | `ruff check src tests benchmarks`, `mypy src` (strict) | 2026-10-27 |
| Wheel and sdist build with assets, docs and license | `uv build`, archives inspected | 2026-10-27 |
| GUI works in a live WebView2 window | manual smoke run: bridge, 7 modes, 4 formats, render selector (`print`/`native`/fixed widths), header preset switches to `native`, 384-dot and 640-px previews | 2026-10-27 |
| CLI works end-to-end | `doctor`, `info`, `convert`, `preview`, `batch` on real files | 2026-10-27 |
| Standalone bundle works | `tdots.exe --version`, `doctor`, `convert` (byte-identical to the venv build), `gui`, and no-argument launch (the double-click path) all verified | 2026-10-27 |
| Raster upscale matches the source size | 6000×4000 JPEG → 384×256 dots → `--upscale auto` → 6144×4096 PNG, same ink | 2026-10-27 |
| Native header output | 6016×4016 JPEG → `--preset header --render-width native` → 6016×4016 1-bit PNG, `screen_export: true`; fixed `--render-width 1920` → 1920×1282; `.bin`/`.txt` rejected. Verified in the venv and the rebuilt `tdots.exe` | 2026-10-27 |
| Real thermal paper output | **not verified — no hardware used** | — |
| CI green on GitHub | workflow added at the repository root; first run happens on the first push | — |

## 13. How to change this plan

1. Change the code first, or decide first — but never let the two diverge.
2. If a numbered requirement changes, edit §4 and the test that proves it in the
   same commit.
3. If an invariant changes, edit §6, update the guard, and regenerate golden
   hashes if the dots changed.
4. Add a row to §7 for any new irreversible decision; leave rejected options in
   place.
5. Update §12 only with evidence you produced yourself.
6. Keep every number reproducible: a command must exist that prints it.
