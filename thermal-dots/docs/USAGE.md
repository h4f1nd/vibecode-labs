# Usage

Everything the app can do, in one place. For the reasoning behind it, read
[PLAN](PLAN.md); for how it works internally, read [ARCHITECTURE](ARCHITECTURE.md).

All commands in this document assume the virtualenv is active
(`.venv\Scripts\activate`) and run in PowerShell. If it is not active, prefix
with `.venv\Scripts\`. The standalone build works the same way — replace `tdots`
with `tdots.exe` and run it from its folder.

---

## 0. Running the app

There are two ways to run it. Neither requires an internet connection.

### From source

```powershell
cd vibecode-labs\thermal-dots
.venv\Scripts\activate
tdots doctor
tdots gui
```

If the environment does not exist yet, create it once:

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
```

Without activating, call the entry point directly:

```powershell
.venv\Scripts\tdots.exe gui
```

### The built standalone app

No Python required. The bundle is a folder; keep it together. Build it with
`build\build.ps1`, or unpack a release archive from the repository's Releases
page.

```powershell
build\nuitka\tdots.dist\tdots.exe gui
```

```powershell
cd build\nuitka\tdots.dist
.\tdots.exe convert photo.jpg -o photo_58.png
.\tdots.exe doctor
```

**Double-clicking `tdots.exe` opens the GUI.** From a terminal, running it with
no arguments prints help instead, because a console is attached — use
`tdots.exe gui` there. Either form works in a shortcut.

---

## 1. Concepts

| Term | Meaning |
|---|---|
| **Dot** | One element the thermal head can fire. 1 bit, no grey. |
| **Paper width** | 58 mm = 384 dots, 80 mm = 576 dots, both at 203 dpi. |
| **`ink`** | The internal bitmap: `True` = printed dot. |
| **Ink ratio** | Percentage of dots that are black. Shown after every conversion. |
| **Dither** | The rule that turns grey pixels into black/white dots. |
| **Sidecar** | The `.json` file written next to each export, recording how it was made. |
| **Preset** | A named set of option values. Explicit flags always override it. |

A useful rule of thumb for photos: aim for an ink ratio of **30–50 %**. Below
15 % the print looks washed out; above 60 % it looks like mud on cheap paper.
`tdots preview` prints the ratio, so you can tune before exporting.

---

## 2. Commands at a glance

| Command | Purpose |
|---|---|
| `tdots convert <image>` | Convert one image to one file |
| `tdots batch <folder>` | Convert every image in a folder |
| `tdots preview <image>` | Render dots as text in the terminal, write nothing |
| `tdots presets` | List built-in presets |
| `tdots doctor` | Show versions, WebView2 status and paper profiles |
| `tdots info <image>` | Show image metadata without converting |
| `tdots gui` | Launch the desktop UI |
| `tdots --version` | Print the version |

Every command supports `--help`:

```powershell
tdots convert --help
```

---

## 3. `tdots convert`

```
tdots convert SOURCE [options]
```

Writes one output file plus a `.json` sidecar. Prints a summary table; add
`--json` for machine-readable output.

### Output

| Option | Default | Meaning |
|---|---|---|
| `--output`, `-o` | `<source>_<paper>_<dither>[_xN].<ext>` | Destination file. Parent folders are created. In render mode the paper label becomes `<width>px`. |
| `--format`, `-f` | `png` | `png`, `bmp`, `bin` (ESC/POS), `txt`. |
| `--sidecar` / `--no-sidecar` | on | Write the `.json` metadata file. |
| `--compress-level` | `6` | PNG compression, 0–9. Higher is smaller and slower. |
| `--upscale` | `1` | PNG/BMP size: `1`–`16`, or `auto` to match the source image's width. |
| `--render-width` | `print` | PNG/BMP canvas: `print` (paper width), `native` (source pixel width), or `8`–`8192` px. |
| `--json` | off | Print the result as JSON instead of a table. |

`--upscale` is a raster-file convenience, applied **after** dithering by
repeating each dot (nearest-neighbour). The pattern does not change; the file
just gets bigger. `auto` chooses the factor closest to the source width, so a
6016 px photo at 58 mm becomes 6144 px wide (16×). It is rejected for `-f bin`
and `-f txt`, because printer bytes must stay at 384/576 dots.

`--render-width` is different: it changes the bitmap's actual sampling width
*before* dithering. `native` uses the source image's pixel width, a number uses
exactly that width. This is how you produce a sharp, full-resolution 1-bit
header or logo with no dither texture:

```powershell
tdots convert logo.png --preset header --render-width native -o header.png
```

The result is a screen/design asset, not a print file. It is rejected for
`-f bin` and `-f txt`; those must stay at the paper width. In render mode the
summary shows `screen export (no paper mapping)` instead of millimetres, and the
sidecar records `"screen_export": true`.

### Paper and geometry

| Option | Default | Meaning |
|---|---|---|
| `--paper`, `-p` | `58` | `58`, `80` or `custom`. |
| `--width`, `-w` | — | Dot width, 8–2048. Use with `-p custom`; with a fixed paper size it must match (384 or 576). |
| `--scale` | `fit` | `fit` (whole image, letterboxed), `fill` (cover, cropped), `stretch` (distorted). |
| `--rotate` | `0` | `0`, `90`, `180`, `270` clockwise. EXIF rotation is applied first. |
| `--margin` | `0` | Blank dots on every side. Must leave at least 8 dots of image width. |
| `--border` | off | Draw a 1-dot frame around the image. |
| `--max-height` | — | Cap the output height in dots. Needed by `fill` and `stretch` on tall images. |

### Tone

| Option | Default | Meaning |
|---|---|---|
| `--gamma` | `1.0` | Tone curve. `>1` adds ink (darker print), `<1` removes ink. Range 0.1–5.0. |
| `--contrast` | `1.0` | Pivot around mid-grey. Range 0.1–4.0. |
| `--brightness` | `0` | −255 to 255, added after contrast. |
| `--invert` | off | Swap light and dark. |
| `--threshold` | `128` | 0–255. For `mean`, `128` means "use Otsu auto"; any other value is a fixed threshold. |

### Dithering

| Option | Default | Meaning |
|---|---|---|
| `--dither`, `-d` | `bayer4` | `bayer4`, `bayer8`, `atkinson`, `fs`, `halftone`, `mean`, `none`. |
| `--preset` | — | Start from a named preset. Flags you type override it. |

### ESC/POS framing (only affects `-f bin`)

| Option | Default | Meaning |
|---|---|---|
| `--init` / `--no-init` | on | Send `ESC @` before the raster blocks. |
| `--feed` | `3` | Feed lines after the image (`ESC d n`). |
| `--cut` | off | Send a full cut (`GS V 0`). |

### Examples

```powershell
# Defaults: 58 mm, bayer4, PNG next to the source
tdots convert photo.jpg

# 80 mm, Floyd-Steinberg
tdots convert photo.jpg -p 80 -d fs -o photo80.png

# Custom 512-dot-wide label
tdots convert label.png -p custom -w 512 -o label_512.png

# Logo: hard threshold, no dithering
tdots convert logo.png -d mean -o logo_1bit.png

# Full-resolution header/logo: source pixel width, no dither noise
tdots convert logo.png --preset header --render-width native -o header.png

# Same clean look, but exactly 1920 px wide
tdots convert logo.png --render-width 1920 -d mean -o header_1920.png

# Raw bytes, no initialise command, 5 feed lines
tdots convert photo.jpg -f bin --no-init --feed 5 -o photo.bin

# Paper simulation for a receipt header: 58 mm, height cap, border
tdots convert header.png --border --max-height 120 -o header.png
```

---

## 4. `tdots batch`

```
tdots batch SOURCE_DIR [options]
```

Converts every image in a folder. A broken file is reported and skipped; the run
continues and the exit code is `1` if anything failed.

| Option | Default | Meaning |
|---|---|---|
| `--out`, `-o` | `out` | Destination folder (created if missing). |
| `--recursive`, `-r` | off | Walk sub-folders. |
| `--upscale` | `1` | PNG/BMP size: `1`–`16`, or `auto` per source file. |
| `--render-width` | `print` | PNG/BMP canvas: `print`, `native` (each source's width), or `8`–`8192` px. |
| every `convert` geometry/tone/dither option | same defaults | Applied to all files. |
| `--sidecar` / `--no-sidecar` | on | Write a `.json` next to each output. |

Batch names files `<source>_<paper>[_xN].<ext>`, or `<source>_<width>px[_xN].<ext>`
in render mode, and always writes ESC/POS with initialise on, 3 feed lines and
no cut. Use `convert` when you need control over the framing bytes.

```powershell
tdots batch .\photos -o .\out -p 80 -d fs
tdots batch .\photos -r --preset newsprint
tdots batch .\logos -o .\headers --render-width native -d mean
```

---

## 5. `tdots preview`

```
tdots preview SOURCE [options]
```

Renders the dots as Unicode half-blocks in the terminal and writes nothing. It
accepts the same geometry and tone options as `convert`, so you can tune here and
reuse the exact same flags for the real export.

| Option | Default | Meaning |
|---|---|---|
| `--columns`, `-c` | `48` | Preview width in characters. |
| `--render-width` | `print` | `native` or a pixel width, for previewing a screen export. |
| all `convert` geometry/tone/dither options | same defaults | Same meaning. |

The first line printed is `width x height dots, ink N %, N ms`.

```powershell
tdots preview photo.jpg -c 56
tdots preview photo.jpg --preset photo-floyd --gamma 1.2
```

---

## 6. `tdots presets`

Lists the six built-in presets.

| Name | Paper | Dither | Gamma | Contrast | Threshold |
|---|---|---|---:|---:|---:|
| `hacker-bayer` | 58 mm | `bayer4` | 1.25 | 1.15 | 128 |
| `photo-floyd` | 58 mm | `fs` | 1.10 | 1.00 | 128 |
| `newsprint` | 58 mm | `halftone` | 1.20 | 1.20 | 128 |
| `line-art` | 58 mm | `mean` | 1.00 | 1.40 | 160 |
| `wide-hacker` | 80 mm | `bayer8` | 1.25 | 1.15 | 128 |
| `header` | 80 mm | `mean` | 1.00 | 1.00 | 128 |

`header` is the clean logo preset: Otsu threshold, no dither texture, no tone
curve. In the GUI it also sets **render** to `native`; on the command line add
`--render-width native` explicitly, or the output stays at the 80 mm dot width.

Presets only set values you did not type on the command line:

```powershell
# dither/gamma/contrast/paper come from the preset; paper=80mm means 576 dots wide
tdots convert photo.jpg --preset wide-hacker

# same preset, but gamma is yours: the flag wins
tdots convert photo.jpg --preset wide-hacker --gamma 1.0
```

---

## 7. `tdots doctor`

Prints Python, Pillow, NumPy and pywebview versions, whether the WebView2 runtime
is installed, the paper profiles and the decoders Pillow can read.

```powershell
tdots doctor
```

Run this first when the GUI refuses to start.

---

## 8. `tdots info`

Reads an image header without decoding the pixels:

```powershell
tdots info photo.jpg
```

```json
{
  "name": "photo.jpg",
  "format": "JPEG",
  "mode": "RGB",
  "width": 6016,
  "height": 4016,
  "has_transparency": false
}
```

---

## 9. `tdots gui`

```powershell
tdots gui
tdots gui --debug
```

| Option | Default | Meaning |
|---|---|---|
| `--width` | `1180` | Window width in pixels. |
| `--height` | `820` | Window height in pixels. |
| `--debug` | off | Open developer tools and log verbosely. |

- Drag and drop images, or press `Ctrl+O`.
- Dither modes are on keys `1`–`7`; `Ctrl+E` exports.
- `1:1` shows real dot size; `paper` simulates thermal paper.
- `size` enlarges the exported PNG/BMP (1×, 2×, 4×, 8× or `auto`); it is
  disabled for `.bin` and `.txt`.
- `render` chooses `print` (paper width), `native` (source width) or a fixed
  pixel width. The `header` preset picks `native` for you. It is disabled for
  `.bin` and `.txt`.
- `height` caps output height in dots, which `fill` and `stretch` need.
- Logs: `%LOCALAPPDATA%\ThermalDots\logs\` (the **logs** button opens it).

---

## 10. Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | `batch` finished with at least one failed file |
| `2` | Invalid options, unreadable source, or a write failure |

Errors print a short message and an actionable hint. The traceback (if any) goes
to the log file, not the terminal.

---

## 11. Recipes

### A photo for 58 mm paper

```powershell
tdots preview photo.jpg --preset photo-floyd
tdots convert photo.jpg --preset photo-floyd -o photo_58.png
```

If the preview reports more than ~55 % ink, add `--gamma 0.9`. If it reports less
than ~20 %, add `--gamma 1.2`.

### A logo or line art

```powershell
tdots convert logo.png -d mean --threshold 160 --border
```

`mean` with a fixed threshold keeps edges sharp; dithering would give the logo a
textured, fuzzy edge.

### A full-resolution header or logo

```powershell
# render at the source image's pixel width, with the clean header preset
tdots convert logo.png --preset header --render-width native -o header.png

# or choose the canvas yourself
tdots convert logo.png --render-width 1920 -d mean -o header_1920.png
```

This is the asset you put in a document, a slide or a design tool: the bitmap is
sampled at that width, so text and logo edges stay sharp. It is **not** a print
file; `-f bin` and `-f txt` reject `--render-width`, because the head only has
384/576 dots.

### An 80 mm photo

```powershell
tdots convert photo.jpg -p 80 -d fs -o photo_80.png
```

### Raw bytes for a print app that accepts ESC/POS

```powershell
tdots convert photo.jpg -f bin -o photo.bin
```

Add `--cut` only if the printer has a cutter and you want the receipt cut after
the image.

### A wide label with a custom head

```powershell
tdots convert label.png -p custom -w 512 -o label.bin -f bin
```

### A big PNG for sharing, not printing

```powershell
# 384-dot print -> 1920 px wide (5x), same dots
tdots convert photo.jpg --upscale 5 -o photo_5x.png

# as close as possible to the source image's pixel width
tdots convert photo.jpg --upscale auto -o photo_original_size.png
```

Use this when the PNG is going into a document, a chat or a design tool. For the
printer itself, keep `--upscale 1` and send the `.bin` (or let your print app
downscale the 1× PNG).

`--upscale` still contains only 384/576 dots worth of detail. For genuinely
sharp text and logo edges at a larger size, use `--render-width` instead; it
renders the bitmap at the larger width rather than repeating print dots.

---

## 12. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Print is all black or all white | Your print app re-dithered the 1-bit PNG. Feed it `.bin`, or disable the app's dithering. |
| Print is inverted (white where black should be) | The pipeline expects inverted bits. Use `--invert`, or check the print app's polarity setting. |
| Photo looks like mud | Thermal dots bloom. Lower the ink: `--gamma 0.8`, or use `--preset photo-floyd`. Aim for 30–50 % ink in `tdots preview`. |
| Print is too pale | Add ink: `--gamma 1.3 --contrast 1.15`, or `--preset hacker-bayer`. |
| Fine detail disappears | 384 dots is about 48 mm at 203 dpi. Crop tighter or use `-p 80`. |
| White seam on one edge with `--scale fill` | Should not happen; the exact-box path is tested. If it does, report it with the source image. |
| `tdots gui` says GUI dependencies are not installed | `pip install "thermal-dots[gui]"`. |
| Double-clicking `tdots.exe` opens no window | The WebView2 runtime is probably missing. Run `tdots.exe doctor` in a terminal; if `webview2` says missing, install the runtime. |
| `tdots gui` complains about WebView2 | Install the Edge WebView2 runtime. `tdots doctor` reports whether it is present. |
| HEIC/HEIF photos are rejected | `pip install "thermal-dots[heif]"`, then reinstall with `-e`. |
| `Cannot overwrite <file> - the file is open in another application.` | Close the file or the print app holding it, or write to another name. |
| Everything feels slow | The first conversion includes decoder warm-up. Re-run `benchmarks\bench.py` and compare. |
| Output is taller than expected | `--max-height` was not set, and `fit` keeps the aspect ratio. Set a height cap. |
| The PNG looks tiny in Explorer or GIMP | It is the exact 384/576-dot print size. Re-export with `--upscale 4` or `--upscale auto` for a bigger file (same dots). |
| A logo/header still looks fuzzy or textured | Use `--preset header --render-width native` (or `-d mean`). Bayer/error diffusion deliberately adds texture; the header preset does not. |
| `render-width only applies to png and bmp output` | `-f bin` and `-f txt` must stay at the paper width. Export a PNG/BMP for the screen asset, and a separate `.bin` for printing. |
| `native rendering needs a source 8 to 8192 px wide` | The source is too small or wider than the screen-export cap. Use an explicit width, for example `--render-width 8192`. |

---

## 13. Where files go

| Thing | Location |
|---|---|
| Default output | Next to the source, `<source>_<paper>_<dither>[_xN].<ext>` (or `<source>_<width>px_<dither>[_xN].<ext>` in render mode) |
| Batch output | `.\out\` unless `--out` says otherwise |
| Sidecar | `<output>.json` |
| GUI logs | `%LOCALAPPDATA%\ThermalDots\logs\` |
