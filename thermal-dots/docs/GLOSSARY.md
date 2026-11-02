# Glossary

One definition per term, using the same names as the code. If you rename a symbol
in `src/thermaldots/`, rename it here in the same commit.

---

## Image and dots

### dot
The smallest printable element. A thermal head either fires at a dot (black) or
does not (paper). There is no grey, which is why dithering exists.

### DPI
Dots per inch. Thermal receipt heads are 203 dpi, so one dot is about 0.125 mm.
58 mm paper gives 384 dots of width, 80 mm gives 576.

### ink
The canonical bitmap used everywhere inside the package:
`numpy.ndarray` of `bool`, shape `(height, width)`, where `True` means the head
fires. Produced by the dither stage; consumed by every exporter. See
`bits.py`.

### ink ratio
`result.ink_ratio` — the fraction of dots that are black. Shown by `tdots preview`
and in every summary. Photos usually look right between 0.30 and 0.50.

### raster
A bitmap laid out row by row. ESC/POS prints rasters; so does BMP.

### row_bytes
Number of bytes one raster row occupies: `ceil(width / 8)`. 48 for 58 mm, 72 for
80 mm. Computed by `bits.bytes_per_row()` and exposed as
`ConversionResult.row_bytes`.

### padding bits
The unused bits at the end of the last byte of a row when the width is not a
multiple of 8. They must be `0`; a set padding bit prints a stray dot at the
right edge.

### polarity
Which bit value means "black". ESC/POS raster uses `1` = dot. Pillow mode `"1"`
uses `1` = **white**, the exact opposite. Mixing them up prints a negative.

---

## Dithering

### dithering
Converting grey levels to black/white dots so that, at viewing distance, the
pattern reads as the original tone. The seven modes live in
`src/thermaldots/dither/`.

### ordered dithering (Bayer)
Compares each pixel against a repeating threshold matrix. `bayer4` uses a 4×4
matrix, `bayer8` an 8×8. Fast, deterministic, and visually structured — the
"cross-hatch" look.

### error diffusion
Pushes the error from each thresholded pixel into its neighbours, so lost
brightness reappears nearby. Sequential by nature, therefore slower.

### Floyd–Steinberg (`fs`)
A specific error-diffusion kernel that spreads error over four neighbours. The
most photographic of the modes. Implemented via Pillow's C path.

### Atkinson
Error diffusion that distributes only 6/8 of the error, discarding the rest. This
produces the high-contrast, shadow-crushing look of early 1-bit printers.
Implemented as a Python loop in `dither/error_diffusion.py`.

### halftone / clustered dot
An ordered matrix where thresholds cluster, producing visible round dots like a
newspaper screen. `halftone` in this project.

### threshold
A single grey value used as the black/white cut-off. `mean` and `none` use it
directly. Default `128`, the midpoint.

### Otsu threshold
An automatic threshold that maximises the variance between the dark and light
groups of the histogram. Used by `mean` when `threshold == 128`.

### LUT (lookup table)
A 256-entry array mapping input grey to output grey. The tone stage builds one
per conversion and applies it with `Image.point()`, so gamma, contrast,
brightness and invert cost one pass over the image.

---

## Tone

### gamma
The exponent applied to normalised luminance. `> 1` makes the image darker and
therefore prints **more ink**; `< 1` prints less. Range 0.1–5.0.

### contrast
Multiplier around mid-grey: `(v - 0.5) * contrast + 0.5`. Range 0.1–4.0.

### brightness
An offset added after contrast, in the 0–255 domain. Range −255–255.

### invert
Reverses light and dark. Useful when a downstream pipeline expects the opposite
polarity.

---

## Geometry

### fit
Scale the image to fit inside the printable area without cropping, preserving
aspect ratio. The remainder becomes blank paper.

### fill
Scale to cover the printable area, then crop the overflow. Guaranteed to fill the
box exactly; uses `ImageOps.fit`.

### stretch
Resize to the box, ignoring aspect ratio. Distorts.

### inner_width
`ConvertOptions.inner_width` — usable width in dots after margins and border:
`resolved_width - 2*margin - 2*border`.

### resolved_width
`ConvertOptions.resolved_width()` — the final dot width: `render_width` when set,
otherwise 384, 576, or the custom `width_dots`. Every output must match it
exactly.

### margin
Blank dots added on every side, inside the paper width.

### border
A 1-dot black frame drawn around the image. Not part of the source image.

### max_height_dots
Optional cap on output height in dots. Without it, `fit` preserves the source
aspect ratio and the output can be very tall.

### draft decode
`Image.draft()` — asking the JPEG decoder for a smaller image before it decodes
the full one. The largest single speed-up in the pipeline.

---

## Options and results

### ConvertOptions
The frozen dataclass holding every value that affects the dots, and nothing
else. Validated in `__post_init__`. New options go here first.

### ConversionResult
The output object: `ink`, `options`, `source`, `timings`, plus helpers
(`png_bytes`, `escpos_bytes`, `half_blocks`, `describe`).

### StageEvent
Progress heartbeat emitted between pipeline stages: `decode`, `fit`, `tone`,
`dither`, `done`.

### preset
A named set of option values in `profiles.PRESETS`. `--preset` applies it, then
any flag typed on the command line overrides the preset's value.

### sidecar
The `.json` file written next to an export: dimensions, options used, byte count,
escape sequences and timings. Delete it if you do not want it (`--no-sidecar`).

### atomic write
`exporters.atomic_write()` — write to a temporary file in the same folder, flush,
then `os.replace()`. A failed or interrupted export never leaves a partial file.

---

## Export formats

### ESC/POS
The command language used by receipt printers. This project emits raster
graphics: `ESC @` (initialise), `GS v 0` (raster block), `ESC d n` (feed),
`GS V 0` (cut).

### `GS v 0`
The raster graphics command: `1D 76 30 00` followed by row bytes and height
(little-endian, 2 bytes each) and then the packed rows.

### fragmentation
Splitting a tall image into several `GS v 0` blocks (960 rows each) because cheap
firmware overruns its buffer on very tall single commands.

### half blocks
The Unicode characters `█ ▀ ▄` used by `-f txt` and `tdots preview`. One
character row represents two dot rows, so a 384×600 bitmap becomes 48×150
characters at `max_width=48`.

### upscale
`--upscale` repeats each dot N times (1–16) for PNG/BMP, or `auto` to choose the
factor closest to the source image's pixel width. Implemented with
`np.repeat`, so it is nearest-neighbour: the file gets bigger, the dots do not
change. It is rejected for ESC/POS and text output.

### render width
`--render-width` / `ConvertOptions.render_width` — an optional canvas width used
by `resolved_width()` instead of the paper width. `native` resolves to the source
image's pixel width; a number is used directly (8–8192). It changes the bitmap
*before* dithering, so the output contains real detail at that width. Raster-only
and labelled a screen export; ESC/POS and text reject it.

### header preset
The `header` preset (`mean`/Otsu, neutral tone, no dither texture) for logos and
text. In the GUI it also switches render mode to `native`; the CLI takes
`--render-width native` explicitly.

---

## GUI

### bridge / API
The `Api` object in `ui/app.py`. pywebview calls its methods from JavaScript and
passes arguments **positionally**; keyword-only parameters would break it.

### handle
An opaque string identifying an uploaded image inside the GUI. `MAX_SOURCES`
handles are kept (`MAX_ITEMS` in `app.js`), and the oldest is evicted.

### private_mode
A pywebview option that gives each GUI launch a clean WebView2 profile, so a
stale cached `index.html` can never be served after a rebuild.

### WebView2
The Microsoft Edge runtime that renders the GUI. Pre-installed on Windows 11;
`tdots doctor` reports whether it is present.

---

## Build and tests

### golden hash
A SHA-256 fingerprint of a converted bitmap, stored in
`tests/golden/hashes.json`. If it changes, visible output changed. Regenerate
deliberately with `python -m tests.golden.regen`.

### invariant
A rule that must never break, even if the code still runs. Listed in
[PLAN](PLAN.md) §6 and [AGENTS](../AGENTS.md), each with the test that guards it.

### preparation / prepared image
The result of decode + geometry: a greyscale image already at the final canvas
size. It is what the cache stores, because it does not depend on dither or tone.

### geometry key
The tuple used to key that cache: width, scale, rotation, margin, border,
max height, max source pixels. Deliberately excludes dither and tone.

### standalone / onefile
Nuitka's two packaging modes. `standalone` is a folder that starts immediately;
`onefile` is a single executable that unpacks on every launch. Standalone is the
default here.

### launcher
`build/launcher.py`, the frozen-build entry point. It exists because Nuitka
compiles the entry script as a top-level module, so `thermaldots/__main__.py`'s
relative import fails inside a frozen binary.

### double-click launch
The frozen exe's no-argument path. `cli._double_clicked()` is true only when the
process is compiled, has no arguments, and owns no console window; in that case
`cli.main()` calls `ui.main()` and the GUI opens. A terminal launch with no
arguments still prints help, because a console is attached.

---

## Documentation

### IN SCOPE / OUT OF SCOPE
The two lists in [PLAN](PLAN.md) §3. Printing and transport are permanently out
of scope; this project converts and stops.

### one fact, one place
Each fact is documented once: flags in [USAGE](USAGE.md), decisions in
[PLAN](PLAN.md), internals in [ARCHITECTURE](ARCHITECTURE.md), vocabulary here.
Everywhere else links to it.
