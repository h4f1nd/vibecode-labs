# Architecture — how `thermal-dots` works today

This describes the code as it is, not as it should be. If the two disagree, the
code wins and this file is the bug. For intent and rules, read
[PLAN](PLAN.md); for user-facing commands, read [USAGE](USAGE.md); for the
vocabulary, read [GLOSSARY](GLOSSARY.md).

---

## 1. Design principles

1. **One pure pipeline.** `convert()` is a function of `(source, options)`. Same
   input and options produce the same `ink` array every time.
2. **One canonical bitmap.** Everything downstream of dithering is
   `ink: numpy.ndarray[bool]`, shape `(height, width)`, `True` = printed dot.
3. **Exporters know nothing about options.** They accept `ink` and return bytes.
   This keeps the dependency graph acyclic: `models → bits → exporters`.
4. **UI code contains no image logic.** The CLI and the GUI are thin adapters
   over the same functions.
5. **Errors are typed and actionable.** `ThermalDotsError` subclasses carry a
   user-safe `message` plus a `hint`. Tracebacks go to the log file only.

## 2. Module map

| Path | Responsibility |
|---|---|
| `src/thermaldots/__init__.py` | Public exports, `__version__` |
| `src/thermaldots/models.py` | `Paper`, `DitherMode`, `ScaleMode`, `OutputFormat`, `ConvertOptions`, `ConversionResult`, `StageEvent` |
| `src/thermaldots/profiles.py` | Paper constants (384/576 dots, 203 dpi), `PRESETS`, `preset_options()` |
| `src/thermaldots/pipeline.py` | `convert()`, decode/cache, `_fit()`, `_tone()`, `_dither()`, `probe()` |
| `src/thermaldots/dither.py` | NumPy kernels: ordered, halftone, Floyd–Steinberg, Atkinson, mean/Otsu |
| `src/thermaldots/bits.py` | `pack_1bit`, `unpack_1bit`, `ink_to_pil`, `pil_to_ink` |
| `src/thermaldots/exporters.py` | PNG/BMP/ESC/POS/text encoders, `atomic_write`, sidecar JSON |
| `src/thermaldots/errors.py` | Error hierarchy with message + hint |
| `src/thermaldots/cli.py` | Typer app, option aliases shared by `convert`/`batch`/`preview` |
| `src/thermaldots/ui/app.py` | pywebview window + `Api` bridge |
| `src/thermaldots/ui/web/` | `index.html`, `style.css`, `app.js` (no build step) |
| `build/launcher.py` | Frozen-build entry point (absolute imports) |
| `build/build.ps1` | Nuitka invocation, one command |
| `build/installer.iss` | Inno Setup script pointing at `build\nuitka\tdots.dist` |

## 3. Data flow

```
             ┌───────────────────────────────────────────────────────┐
 source ───► │ decode                                                │
 (path,      │  1. Image.open()      header only, no pixels yet      │
  bytes,     │  2. size guard        > 120 MP → ImageTooLargeError   │
  stream,    │  3. draft()           JPEG/MPO only: ask the decoder   │
  PIL,       │                       for target width before decoding│
  ndarray)   │  4. load()            decode at the reduced size      │
             │  5. prepare()         EXIF rotate → rotate → grey →    │
             │                       flatten alpha on white → _fit() │
             └───────────────────────────┬───────────────────────────┘
                                         ▼
             ┌───────────────────────────────────────────────────────┐
             │ tone      LUT over 256 values: gamma, contrast,        │
             │           brightness, invert → 8-bit grey image        │
             └───────────────────────────┬───────────────────────────┘
                                         ▼
             ┌───────────────────────────────────────────────────────┐
             │ dither    one NumPy kernel → ink: bool[height, width]  │
             └───────────────────────────┬───────────────────────────┘
                                         ▼
             ┌───────────────────────────────────────────────────────┐
             │ export    png │ bmp │ escpos │ txt  (+ JSON sidecar)    │
             └───────────────────────────────────────────────────────┘
```

Timings are recorded per stage in `ConversionResult.timings` (`decode`, `tone`,
`dither`, `total`). `total` is measured once and is not the sum of the others;
`ConversionResult.total_ms` prefers it.

## 4. Decode and geometry

### 4.1 Decode order matters

`Image.open()` reads the header only. Two things happen before pixels are
decoded:

- **Size guard** (`max_source_pixels`, default 120 000 000) rejects decompression
  bombs before they allocate.
- **Draft** (`Image.draft`) asks libjpeg for a downscaled decode. A 24 MP photo
  destined for 384 dots is decoded at roughly 1/6 scale, which is where the
  142 ms → 31 ms improvement comes from. Only `JPEG` and `MPO` support it; other
  formats fall through unchanged.

### 4.2 Geometry math

Let `W = options.resolved_width()` (384, 576, a custom value, or
`render_width` when native rendering is on) and

```
inner = W − 2·margin − 2·border
```

1. `fit` — scale by `min(inner/w, box_h/h)`, preserving aspect ratio.
2. `fill` — `ImageOps.fit(image, (inner, box_h))`: scale to cover, then crop.
3. `stretch` — `resize((inner, box_h))`, ignoring aspect ratio.

`box_h` is `max_height_dots` if set, otherwise the aspect-implied height. A
canvas of width `W` is created and filled with white; the resized image is
pasted centred horizontally, with `margin + border` dots of top padding. The
border is a 1-dot black rectangle drawn around the pasted image.

Why `ImageOps.fit` for `fill`: computing the crop manually leaves a one-dot gap
when the scaled size rounds down, and `Image.crop()` pads out-of-bounds areas
with **black**, which prints as a solid edge. `ImageOps.fit` always returns
exactly the requested box.

### 4.3 Resampling

LANCZOS for every resize. Shrinking a photo to 384 dots throws away ~94 % of the
pixels; LANCZOS keeps edges and fine texture better than BILINEAR or NEAREST,
which matters more than the small speed difference.

`render_width` therefore changes the input to resampling, not its output. A
6000 px source at `--render-width native` is fitted to a 6000-dot canvas: text
and logo edges keep the source's detail, and `mean`/Otsu produces a clean 1-bit
asset. At `--render-width print` the same source is fitted to 384/576 dots, which
is why the default output looks small in an image viewer. Native rendering is a
screen export; the pipeline does not pretend those dots map to millimetres.

### 4.4 Colour handling

- `RGB`, `L`, `P` → `convert("L")`
- `RGBA`, `LA`, `PA`, `P` with transparency → composited onto **white**
- `I;16`, `I`, `F` → scaled by peak value, not by a fixed 65535
- `CMYK` → `RGB` → `L`

Alpha over white matters: transparent pixels must become paper, not ink.

## 5. Tone

One 256-entry lookup table is built per conversion and applied with
`Image.point()`:

```python
ramp = (v / 255) ** gamma          # v = 0..255
ramp = (ramp - 0.5) * contrast + 0.5
ramp = ramp * 255 + brightness
if invert:
    ramp = 255 - ramp
lut = clip(ramp, 0, 255).astype(uint8)
```

Consequences worth knowing:

- `gamma > 1` **darkens** the print (more ink), `gamma < 1` lightens it. The
  curve is applied to luminance, where higher = brighter, and dithering turns
  darkness into dots.
- `contrast` pivots around mid-grey (0.5), so it does not shift overall
  brightness much.
- If all tone options are neutral, the LUT step is skipped entirely.

## 6. Dithering

All kernels take `gray: uint8[H, W]` and return `bool[H, W]` where `True` fires
the head.

| Mode | Kernel | Character | Cost |
|---|---|---|---|
| `bayer4` | 4×4 ordered matrix | Structured, stable, small-scale pattern | NumPy, fast |
| `bayer8` | 8×8 ordered matrix | Finer pattern, less visible structure | NumPy, fast |
| `halftone` | 8×8 clustered-dot matrix | Newspaper look; large blobs | NumPy, fast |
| `mean` | Global threshold (Otsu when auto) | Hard black/white, best for logos and text | NumPy, fast |
| `none` | Fixed threshold (`--threshold`) | No dithering at all; pure threshold | NumPy, fast |
| `fs` | Floyd–Steinberg error diffusion | Photographic detail, some noise | Pillow C path, fast |
| `atkinson` | Atkinson error diffusion | Lighter, higher contrast, classic Mac look | Python loop |

Notes:

- `mean` uses Otsu's method when `threshold == 128` (the CLI's "auto" signal) and
  the literal threshold otherwise. Otsu picks the value that maximises
  between-class variance of the histogram.
- Atkinson diffuses only 6/8 of the error, which is why it looks lighter and
  loses shadow detail by design.
- Atkinson is ~3× slower than the others because error diffusion is sequential.
  It operates on a padded Python list; a NumPy rewrite was not worth the
  complexity for a 100 ms operation.

## 7. Bit polarity — the trap

There are two conventions in play, and they are opposites:

| Context | Meaning of bit `1` |
|---|---|
| ESC/POS `GS v 0` raster | **printed dot** (black) |
| Pillow mode `"1"` | pixel value 255 = **white** |

`pack_1bit()` emits the ESC/POS convention: MSB first, rows padded to a byte
boundary with `0` bits. `ink_to_pil()` inverts the array before handing it to
Pillow, so an `ink=True` dot becomes a black pixel in the PNG.

The practical consequence:

```text
ink row:       1 0 1 0 1 0 1 0   →  0xAA   (what ESC/POS wants)
PIL .tobytes():0 1 0 1 0 1 0 1   →  0x55   (bitwise complement)
```

Never write `PIL.Image.tobytes()` into a `.bin` file. Use `pack_1bit` /
`result.escpos_bytes()`.

## 8. Exporters

| Function | Output | Notes |
|---|---|---|
| `png_bytes(ink, compress_level=6, upscale=1)` | 1-bit PNG | Exact dot dimensions by default; `upscale` repeats dots |
| `bmp_bytes(ink, upscale=1)` | 1-bit BMP | Safest for legacy Windows print pipelines |
| `escpos_bytes(ink, init, feed_lines, cut, fragment_rows=960)` | Raw ESC/POS | See layout below; never upscaled |
| `half_block_text(ink, max_width=48)` | UTF-8 text | `█ ▀ ▄` pairs; two dot rows per character row |
| `write_sidecar(path, metadata)` | `<output>.json` | Source, options, sizes, ink ratio, timings |

### Raster upscale

`upscale_ink(ink, factor)` is `np.repeat` on both axes: every dot becomes a
`factor × factor` block. It runs **after** dithering, so:

- `ink` is unchanged, and `.bin` output is byte-for-byte identical at any factor;
- the PNG/BMP gains pixels, not detail — smooth resampling would introduce greys
  that a 1-bit image cannot represent;
- it is not part of the cache key, because it does not affect the bitmap.

The sidecar records `upscale`, `pixel_width` and `pixel_height`; `width` and
`height` stay the printer's dot dimensions.

### Native render width

`--render-width` is the opposite trade-off: it changes the bitmap before
dithering, so the output has real detail at that width. `native` resolves to the
source image's pixel width (8–8192), and an explicit number is used as-is.
`ConvertOptions.resolved_width()` prefers `render_width`, so the fit, canvas,
`ink` shape, sidecar `width` and filenames all agree.

Because the result is not tied to a print head, the CLI rejects it for
`-f bin` and `-f txt`, prints `screen export (no paper mapping)` instead of
millimetres, and writes `"screen_export": true` in the sidecar. `--upscale` may
still be used on top, though `auto` resolves to 1× at native width (the dot
width already matches the source).


### ESC/POS layout

```
ESC @                      1B 40           initialise (optional)
  ┌ per 960-row band ─────────────────────────────────────┐
  │ GS v 0 0               1D 76 30 00      raster command │
  │ xL xH                  row bytes, LE                   │
  │ yL yH                  band height, LE                 │
  │ data                   rows × row_bytes, MSB first     │
  └────────────────────────────────────────────────────────┘
ESC d n                    1B 64 nn        feed n lines (optional)
GS V 0                     1D 56 00        full cut (optional)
```

`fragment_rows=960` exists because cheap clone firmware overruns its receive
buffer above roughly 1000 rows per raster command. Splitting is invisible to the
printer: consecutive bands are printed contiguously.

## 9. Writing files

`atomic_write()` writes to a temporary file in the destination directory, calls
`fsync`, then `os.replace()`. Three failure modes are mapped deliberately:

| Situation | Error | User message |
|---|---|---|
| Destination folder cannot be created | `OutputError` | `Cannot create <folder>: …` |
| Destination file is open/locked | `OutputInUseError` | `Cannot overwrite <file> - the file is open in another application.` |
| Any other OS write failure | `OutputError` | `Cannot write <file>: …` |

The temp file is removed on every failure path, so a crashed export never leaves
a `.<name>-xxxx.png.tmp` behind.

## 10. Caching

Two keys exist, both built from **geometry only**:

- On disk: `(resolved path, mtime_ns, size, geometry)`
- In memory (GUI uploads): `("mem", handle, geometry)`

```
geometry = (resolved_width, scale, rotate, margin, border, max_height, max_source_pixels)
```

Dither mode and tone are *not* in the key. That is the whole point: dragging the
gamma slider reuses the prepared image and only re-runs the LUT and the kernel
(~5 ms on a 24 MP photo instead of ~55 ms for a fresh decode). Raster upscale is
also absent: it is applied by the exporter, after `ink` exists. `render_width` is
present indirectly through `resolved_width()`, so switching between print and
native rendering correctly invalidates the prepared image.

The cache holds at most `_CACHE_LIMIT = 4` prepared images in an `OrderedDict`
and is guarded by `_cache_lock`. Eviction is least-recently-used. `clear_cache()`
empties it; tests call it between cases.

## 11. GUI

`ui/app.py` creates one window (`1180×820`, resizable) and one `Api` object.

| Method | Signature | Returns |
|---|---|---|
| `bootstrap` | `()` | modes, formats, presets, papers, `max_sources` |
| `load_image` | `(data_url, name)` | `{ok, handle, name, bytes, source}` where `source` is the `probe()` metadata |
| `preview` | `(handle, options)` | `{ok, image, width, height, row_bytes, raster_bytes, ink_ratio, ms, mm, print_seconds, screen}` |
| `export` | `(handle, options, fmt, sidecar, escpos, upscale)` | `{ok, path, bytes, format, upscale, pixel_width, pixel_height, screen}` or `{ok: false, cancelled}` |
| `reveal_logs` | `()` | `{ok, path}` |

Rules:

- Arguments are **positional** because pywebview calls them positionally; a test
  enforces that `export` has no keyword-only parameters.
- Errors are returned as `{ok: false, error, message, hint}` — never raised
  across the bridge, because a Python traceback in the console is invisible to
  the user.
- At most `MAX_SOURCES = 8` uploads are retained (`app.js` mirrors this as
  `MAX_ITEMS = 8`), so a long session cannot grow without limit.
- `private_mode=True` gives every launch a clean WebView2 profile. Without it,
  WebView2's disk cache served a stale `index.html` after a rebuild.
- Assets resolve via `Path(__file__).resolve().parent / "web"`, which is also
  correct in the frozen build because Nuitka places package data at
  `<dist>/thermaldots/ui/web`.

## 12. Packaging

```
pip install -e ".[dev,gui]"   → console script tdots = thermaldots.cli:main
build\build.ps1               → Nuitka standalone → build\nuitka\tdots.dist\tdots.exe
build\installer.iss           → Inno Setup installer (optional)
```

Three ways to launch, all backed by the same `cli.main()`:

| Situation | Command | Result |
|---|---|---|
| Source checkout | `tdots gui` | GUI |
| Terminal, frozen build | `build\nuitka\tdots.dist\tdots.exe gui` | GUI |
| Explorer, frozen build | double-click `tdots.exe` | GUI |
| Terminal, frozen build, no args | `tdots.exe` | CLI help (console attached) |

The frozen build uses `build/launcher.py`, not `src/thermaldots/__main__.py`.

Why: Nuitka compiles the entry script as a **top-level module**, so a relative
import (`from .cli import main`) raises
`ImportError: attempted relative import with no known parent package` at
start-up. The launcher uses an absolute import and mirrors the console script.

`--windows-console-mode=attach` means:

- launched from a terminal → CLI output appears in that terminal;
- launched from Explorer → no console window, so the GUI looks native.

The frozen entry point decides between the two: with no arguments and no console
attached, `cli.main()` calls `ui.main()` directly; otherwise it runs the CLI. A
terminal launch with no arguments therefore still prints help.

Nuitka 4.x has a built-in pywebview plugin that pulls in `webview`, `pythonnet`,
`clr_loader` and the WebView2 loader. Do **not** list those packages explicitly;
doing so conflicts with the plugin.

## 13. Threading and cancellation

- Conversion itself is single-threaded and re-entrant.
- The only shared state is the prepared-image cache, protected by a lock.
- `CancellationToken` is checked between stages (decode, fit, tone, dither).
  A cancelled conversion raises `ConversionCancelled` and writes nothing.
- The GUI runs conversions on pywebview's worker thread; the UI never blocks.

## 14. Where to look when something breaks

| Symptom | First place to look |
|---|---|
| Printed output is inverted | `bits.ink_to_pil` / `bits.pack_1bit` (§7) |
| White seam on one edge with `fill` | `pipeline._fit` (§4.2) |
| Slider drag feels slow | cache key in `pipeline._geometry_key` (§10) |
| ESC/POS prints garbage on one printer | `fragment_rows` in `exporters.escpos_bytes` (§8) |
| GUI shows old markup after an edit | `private_mode` in `ui/app.py` (§11) |
| Exported PNG looks tiny | That is the dot grid; see raster upscale (§8) or native render width (§8) |
| Native logo looks soft or fuzzy | `mean`/Otsu (the `header` preset) is intentional; dither modes add texture |
| Frozen exe dies immediately | `build/launcher.py` and `build.ps1` (§12) |
