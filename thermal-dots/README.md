# THERMAL//DOTS

```
                 ▄▄▄▄▄▄▄
   THERMAL//DOTS █ ▄▀▄ █   images → dots
                 ▀▀▀▀▀▀▀
```

Convert an image into the exact 1-bit dots a 58 mm (384 dots) or 80 mm (576 dots)
ESC/POS thermal printer prints. Use the command line or the desktop GUI.

**This app does not print.** It writes PNG, BMP, raw ESC/POS or text files; your
existing print app sends them to the printer.

- Exact dot widths: 384 and 576, plus custom widths.
- Seven dither modes, including the Bayer matrix look and Floyd–Steinberg.
- Clean, full-resolution logo/header exports (`--render-width native`) when you
  want a screen asset instead of a print grid.
- Four export formats, with a JSON sidecar describing exactly how each file was
  made.
- One engine behind both the CLI and the GUI, so the preview is the exported
  bitmap.

Part of [vibecode-labs](../README.md), a two-project lab; the sibling app is
[DOTDAT](../dotdat/README.md), a read-only Clarion `.DAT` viewer.

---

## Install

Requires **Python 3.11+**. Developed and tested on Windows 11 with Python 3.14.

From the project folder:

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
```

Without `uv`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"
```

Activate the environment once per terminal:

```powershell
.venv\Scripts\activate
```

The GUI needs the **Microsoft Edge WebView2 runtime**, which is pre-installed on
Windows 11. `tdots doctor` tells you whether it is present.

---

## Run

### The built app (no Python needed)

Build the standalone folder once (see
[Build a standalone Windows exe](#build-a-standalone-windows-exe)), then run
from it. Paths below are relative to this project folder; from a fresh clone
that is `vibecode-labs\thermal-dots`.

```powershell
cd build\nuitka\tdots.dist
.\tdots.exe gui
.\tdots.exe convert photo.jpg -o photo_58.png
.\tdots.exe preview photo.jpg -c 56
.\tdots.exe doctor
```

Double-clicking `tdots.exe` opens the GUI. From a terminal, no arguments prints
help instead (a console is attached), so use `gui` there explicitly.

A shortcut is optional, with either target:

- `build\nuitka\tdots.dist\tdots.exe` — same as double-clicking
- `build\nuitka\tdots.dist\tdots.exe gui` — explicit

Prebuilt release archives are published on the repository's Releases page; they
contain the same `tdots.dist` folder.

### From source

```powershell
cd vibecode-labs\thermal-dots
.venv\Scripts\activate
tdots doctor
tdots gui
```

Without activating first:

```powershell
.venv\Scripts\tdots.exe gui
```

---

## Quick start

Commands below assume the venv is active (see **Run** above).

```powershell
# 58 mm, Bayer 4x4 (default) -> photo_58mm_bayer4.png
tdots convert photo.jpg

# 80 mm, Floyd-Steinberg, explicit output
tdots convert photo.jpg -p 80 -d fs -o photo_80.png

# start from a preset, then override one value
tdots convert photo.jpg --preset newsprint --gamma 0.8

# raw ESC/POS bytes for your print app
tdots convert photo.jpg -f bin -o photo.bin

# a full-HD-ish PNG with the same dots (auto matches the source width)
tdots convert photo.jpg --upscale auto -o photo_hd.png

# clean full-resolution logo/header (screen asset, no dither noise)
tdots convert logo.png --preset header --render-width native -o header.png

# look at the dots before writing a file
tdots preview photo.jpg -c 56

# inspect an image without converting it
tdots info photo.jpg

# convert a whole folder; one broken file does not stop the rest
tdots batch .\photos -o .\out -p 58 -d bayer4

# desktop UI
tdots gui
```

Default output names follow `<source>_<paper>_<dither>.<ext>`, for example
`photo_58mm_bayer4.png`. With `--upscale` above 1 the factor is added:
`photo_58mm_bayer4_x4.png`. Native rendering replaces the paper label with the
pixel width: `logo_6000px_mean.png`.

Full flag reference, recipes and troubleshooting: [docs/USAGE.md](docs/USAGE.md).

---

## Build a standalone Windows exe

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File build\build.ps1
```

Output: `build\nuitka\tdots.dist\` — a folder containing `tdots.exe` and its
runtime files. Add `-OneFile` for a single executable; it unpacks on every
launch, which is noticeable for the GUI. `build\installer.iss` can be compiled
with Inno Setup afterwards.

---

## Output formats

| Format | Flag | Use it when |
|---|---|---|
| 1-bit PNG | `-f png` (default) | Your print app accepts images and passes 1-bit data through untouched. |
| 1-bit BMP | `-f bmp` | Your print app uses a legacy Windows/GDI path that mishandles 1-bit PNG. |
| Raw ESC/POS | `-f bin` | Your print app accepts bytes. Nothing can re-dither it. |
| Text art | `-f txt` | Documentation, terminal previews, typewriter-style output. |

Every file is written atomically (temp file, then replace), so a failed export
never leaves a half-written image where a print job expects one.

A 1-bit PNG is **already dithered**. If your print app dithers it again, quality
is destroyed twice — feed it `.bin`, or configure the print app to pass 1-bit
images through unchanged.

### ESC/POS byte contract

```
ESC @                      initialise            --init      (default on)
GS v 0 0 xL xH yL yH       raster block header
<48 or 72 bytes per row>   payload, MSB first, rows padded to a byte
ESC d n                    feed n lines          --feed      (default 3)
GS V 0                     full cut              --cut       (default off)
```

- `xL/xH` is `ceil(width / 8)` little-endian: 48 bytes for 58 mm, 72 for 80 mm.
- Images taller than 960 rows are split into several `GS v 0` blocks; cheap clone
  firmware overruns its buffer on very tall single blocks.
- `PIL.Image.tobytes()` on a mode `"1"` image is **not** this payload. Pillow
  stores 1 as white, so its bytes are the bitwise complement of the ESC/POS
  raster. `thermal-dots` has its own packer for this reason.

Each export also writes `<output>.json` with dot dimensions, options, byte counts
and timings. Disable it with `--no-sidecar`.

### Output size

By default a PNG or BMP is written at the printer's **exact dot size**: 384
pixels wide for 58 mm, 576 for 80 mm. That is the correct file to print, but it
looks tiny in an image viewer.

`--upscale` makes the raster file bigger without changing a single dot:

```powershell
tdots convert photo.jpg --upscale 4 -o photo_4x.png
tdots convert photo.jpg --upscale auto -o photo_original_size.png
```

- `1`–`16` repeats every dot that many times (nearest-neighbour).
- `auto` picks the factor whose output width is closest to the **source
  image's** pixel width, clamped to 1–16.

A 384-dot print becomes 1920 px wide at `--upscale 5`, and about 6144 px at 16.
Each dot is a crisp N×N block: the pattern is identical, because interpolation
would invent greys that a 1-bit file cannot store. This enlarges the file, not
the detail — the print head still has 384/576 dots across.

Raster only: `--upscale` is rejected for `-f bin` and `-f txt`. The `.bin` your
print app receives is always the original dot grid.

### Clean header or logo at full resolution

`--upscale` enlarges the 384/576-dot pattern. If you want the bitmap itself to
be sampled at the image's real pixel width — sharp text and logos, no dither
texture, no visible enlargement blocks — use `--render-width`:

```powershell
tdots convert logo.png --preset header --render-width native -o header.png
```

- `native` renders at the source image's pixel width (8–8192 px).
- A number renders at exactly that width, for example `--render-width 1920`.
- `print` (the default) keeps the paper width.

`--preset header` uses Otsu thresholding (`mean`), neutral gamma and contrast,
and 80 mm metadata: black stays black, white stays white, and no Bayer or
error-diffusion texture is added. Combined with `--render-width native`, a
6000 px logo stays 6000 px with clean edges — the look of a 1-bit asset from
GIMP or Canva, not a magnified print preview.

`--render-width` is rejected for `-f bin` and `-f txt`. Those outputs must stay
at 384/576 dots, because the print head cannot use more. This is a screen and
design export, not a replacement for the print path.

---

## Dither modes

| Mode | What it does | Best for |
|---|---|---|
| `bayer4` (default) | 4×4 ordered Bayer matrix | the crisp retro cross-hatch look |
| `bayer8` | 8×8 ordered Bayer matrix | photos that still need texture |
| `atkinson` | error diffusion, 6 neighbours | high-contrast early-Mac look |
| `fs` | Floyd–Steinberg error diffusion | the most photographic detail |
| `halftone` | 8×8 clustered-dot screen | newspaper and comic style |
| `mean` | Otsu auto threshold (`--threshold` to override) | logos, line art, text |
| `none` | fixed threshold, no dithering | input that is already 1-bit |

Tone controls: `--gamma` (`>1` adds ink and darkens the print, `<1` lightens it),
`--contrast`, `--brightness`, `--invert`.
Geometry: `--scale fit|fill|stretch`, `--rotate 0|90|180|270`, `--margin`,
`--border`, `--max-height`.

Presets: `hacker-bayer`, `photo-floyd`, `newsprint`, `line-art`, `wide-hacker`,
`header`. List them with `tdots presets`. A flag you type always beats the
preset.

---

## GUI

```powershell
tdots gui
```

- Drag and drop, or `Ctrl+O` — up to 8 images at once.
- The preview is rendered from the **exported bitmap**, not a CSS approximation.
- `1:1` shows real dot size; `paper` simulates thermal paper.
- Dither modes on keys `1`–`7`; export on `Ctrl+E`.
- The **size** selector enlarges the exported PNG/BMP (1×, 2×, 4×, 8× or
  `auto` to match the source); it is disabled for `.bin` and `.txt`.
- The **render** selector chooses `print` (paper width), `native` (source
  width), or a fixed pixel width. The `header` preset selects `native`
  automatically.
- Presets use the same names as `--preset`.
- `height` caps the print in dots — needed before `fill` and `stretch` do
  anything.
- Logs live in `%LOCALAPPDATA%\ThermalDots\logs\` (the **logs** button).

---

## Performance

Measured on a 4000×3000 (12 MP) JPEG, cold cache, median of 5, on a 4-core
laptop CPU: **31 ms at 58 mm** and **44 ms at 80 mm** with the default `bayer4`.
Atkinson, the only Python loop in the pipeline, takes 81 / 151 ms.

Decoded images are cached by `(path, mtime, size, geometry)`, so changing the
dither mode or gamma does not re-read the file. In the GUI a slider tick on a
24 MP photo costs about **5 ms** after the first load.

Reproduce it:

```powershell
.venv\Scripts\python benchmarks\bench.py --repeat 5
```

Full table, methodology and the reason for each number: [docs/PLAN.md](docs/PLAN.md#9-performance).

---

## Does not print

There is no USB, serial, Bluetooth, network or driver code in this project, and
none will be added. It converts; something else prints.

That boundary is deliberate: transport code means device support, drivers and
firmware quirks, and it would make every conversion result depend on hardware.
Your print app stays in charge of the printer.

---

## Documentation

| File | What it answers |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | What this app is for, what is out of scope, decisions, risks, roadmap |
| [docs/USAGE.md](docs/USAGE.md) | Every command and flag, recipes, troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pipeline works, bit polarity, caching, packaging |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Terms used in the docs and the code |
| [AGENTS.md](AGENTS.md) | Repo map, commands and invariants for AI agents |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, quality gates, how to change dithering safely |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

---

## Status

What has actually been verified, and what has not.

| Area | State |
|---|---|
| Conversion engine, CLI, GUI | tested (`pytest`, see [CONTRIBUTING](CONTRIBUTING.md)) |
| Lint and strict types | clean (`ruff`, `mypy --strict`) |
| Python wheel with web assets | builds and installs |
| Live GUI in WebView2 | manually smoke-tested |
| Standalone `.exe` (Nuitka) | builds, starts, GUI window verified, byte-identical output to the venv build |
| Real thermal paper | **not verified — no hardware was used** |
| CI on GitHub | workflow runs on every push to `main` and pull request that touches this folder |

Only Windows 11 has been tested. The engine itself is portable; the GUI depends
on WebView2.

---

## License

MIT — see [LICENSE](LICENSE).
