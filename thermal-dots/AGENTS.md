# AGENTS.md

Instructions for AI coding agents working on `thermal-dots`. Humans are welcome
to read it too; [CONTRIBUTING.md](CONTRIBUTING.md) has the same rules with more
prose.

Project: `thermal-dots` — converts images to 1-bit dot data for 58 mm (384 dots)
and 80 mm (576 dots) ESC/POS thermal printers. Conversion only. It never prints.
This folder is one half of the `vibecode-labs` repository; the sibling app is
[DOTDAT](../dotdat/README.md).

## Commands

Copy these exactly. Windows PowerShell, run from **this folder**
(`vibecode-labs\thermal-dots`), virtualenv at `.venv`.

```text
setup:   uv venv .venv; uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
test:    .venv\Scripts\python -m pytest
lint:    .venv\Scripts\ruff check src tests benchmarks
types:   .venv\Scripts\mypy src
js:      node --check src\thermaldots\ui\web\app.js
bench:   .venv\Scripts\python benchmarks\bench.py --repeat 5
run cli: .venv\Scripts\tdots.exe convert <image> -o out.png
run gui: .venv\Scripts\tdots.exe gui
run exe: build\nuitka\tdots.dist\tdots.exe gui
dbl-click: tdots.dist\tdots.exe (no arguments, no console) opens the GUI
wheel:   uv build --wheel
exe:     powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1 -SkipInstall
```

All of `test`, `lint` and `types` must pass before a change is considered done.

## Repo map

| Path | Responsibility | Read it when |
|---|---|---|
| `src/thermaldots/models.py` | Options, enums, result object, validation | Changing any option |
| `src/thermaldots/pipeline.py` | `convert()`: decode → fit → tone → dither, cache | Changing image handling or speed |
| `src/thermaldots/dither/` | Ordered, halftone, threshold, error-diffusion kernels | Changing how dots are chosen |
| `src/thermaldots/bits.py` | 1-bit packing and Pillow conversion | Anything involving polarity |
| `src/thermaldots/exporters.py` | PNG/BMP/ESC/POS/text, atomic writes, sidecars | Changing output bytes |
| `src/thermaldots/profiles.py` | Paper constants and the six presets | Adding a preset |
| `src/thermaldots/cli.py` | Typer commands and shared option aliases | Adding or renaming a flag |
| `src/thermaldots/ui/app.py` | pywebview window and JS bridge | Changing the GUI API |
| `src/thermaldots/ui/web/` | `index.html`, `style.css`, `app.js`, no build step | Changing the GUI |
| `tests/golden/` | 17 dot-pattern fingerprints + regeneration script | After an intentional dither change |
| `build/` | Nuitka + Inno Setup scripts, frozen entry point | Packaging |
| `docs/` | Plan, architecture, usage, glossary | Before changing behaviour |

## Invariants — never break these

1. `ink` is `bool[height, width]`; `True` means the thermal head fires.
   Guarded by `tests/test_bits.py`.
2. ESC/POS raster: MSB first, bit `1` = dot. Pillow mode `"1"`: bit `1` = white.
   `ink_to_pil` inverts. Guarded by `tests/test_bits.py` and
   `tests/test_exporters.py`.
3. Never write `PIL.Image.tobytes()` as ESC/POS. It is the bitwise complement.
4. Row padding bits in a raster row are always `0`, at any width.
5. Output width equals `ConvertOptions.resolved_width()`, exactly, including
   margins and border.
6. The decoded-image cache key covers geometry only — never dither or tone.
   Dither and tone must be re-applied to cached pixels.
7. pywebview bridge methods stay positionally callable. `Api.export` is
   `export(handle, options, fmt, sidecar, escpos, upscale)` with no keyword-only
   parameters; `tests/test_ui_api.py` enforces this.
8. `convert()` stays pure. No network, no global mutable state besides the
   bounded image cache, no writing files.
9. Converted output stays deterministic. Same input + same options ⇒ identical
   bytes.
10. Raster upscale is presentational and post-dither: `exporters.upscale_ink`
    repeats dots with `np.repeat`. It must never enter the cache key, mutate
    `ink`, or change `.bin` bytes.
11. Native render width is pre-dither sampling, not upscaling. `render_width`
    takes precedence in `resolved_width()`, so it changes the cache key along
    with the bitmap, filenames and sidecar. It is raster-only: never allow it
    to produce ESC/POS or text output.

## Conventions

- Python 3.11+ syntax, `from __future__ import annotations`, full type hints.
  `mypy --strict` on `src`.
- Line length 100. Ruff rules `E F I UP B SIM RUF`.
- Options live on `ConvertOptions`; nothing else. New option ⇒ `models.py`
  validation + `cli.py` flag + `docs/USAGE.md` + `tests/test_docs.py` passes.
- The frozen exe with no arguments and no console opens the GUI
  (`cli._double_clicked`). Keep that behaviour; a terminal launch must still
  print help.
- Errors: raise a `ThermalDotsError` subclass with a user-safe `message` and an
  actionable `hint`. Never leak a traceback into CLI or GUI output.
- Comments explain *why*, not *what*. Keep the existing "why" comments; they
  record bugs that were actually hit (Pillow polarity, `ImageOps.fit`, stale
  WebView2 cache, Nuitka relative import).
- Docs are tested. `tests/test_docs.py` verifies documented flags and links, so
  renaming a flag means updating `docs/USAGE.md` in the same change.
- Do not add a dependency without a reason recorded in `docs/PLAN.md` §7.
- Do not add printing, transport, device discovery or any network call. It is
  out of scope by design (`docs/PLAN.md` §3).

## Changing dithering

1. Edit the kernel.
2. Run `pytest tests/test_dither.py`.
3. If the dot pattern changed intentionally, regenerate fingerprints:
   `.venv\Scripts\python -m tests.golden.regen`
4. Review the `tests/golden/hashes.json` diff. Every changed hash is a visible
   change for every user.
5. Re-run the benchmark and update the table in `docs/PLAN.md` §9 with real
   numbers.

## Known gaps

- CI is defined at the repository root (`.github/workflows/thermal-dots.yml`)
  and is scoped to this folder; the first green run happens after the first push.
- Real thermal paper output is unverified; only bytes are guaranteed.
- Windows-only testing. The engine is portable; the GUI needs WebView2.
- `atkinson` is a Python loop and is about 3× slower than every other mode. That
  is accepted, not a bug.

## When you are unsure

Read `docs/PLAN.md` §4 (requirements) and §6 (invariants) first. If a requested
change contradicts them, say so instead of silently changing the rules.
