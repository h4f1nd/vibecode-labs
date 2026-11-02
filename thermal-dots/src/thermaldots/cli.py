"""Command line interface (Typer + Rich).

The CLI is the reference front-end: it exercises exactly the same engine the
GUI uses, which makes it the fastest way to validate a printer profile.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import __version__
from .errors import InvalidOptionsError, ThermalDotsError
from .exporters import atomic_write, write_sidecar
from .models import (
    RENDER_WIDTH_MAX,
    ConversionResult,
    ConvertOptions,
    OutputFormat,
    Paper,
    parse_upscale,
    resolve_upscale,
)
from .pipeline import convert as run_convert
from .pipeline import probe
from .profiles import PRESETS, list_papers

IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".ppm",
    ".ico",
    ".avif",
    ".heic",
    ".heif",
}

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Convert images into 1-bit dot-matrix output for thermal printers.",
)
console = Console()
err_console = Console(stderr=True)

# Shared option aliases.  Declaring them once keeps `convert`, `batch` and
# `preview` in sync - a preview is only useful if it accepts the same knobs as
# the conversion it is previewing.
#
# Note: with `Annotated`, typer.Option() must *not* carry the default value as
# its first positional argument (it would be parsed as an extra param name); the
# default lives on the function signature only.
PaperOpt = Annotated[str, typer.Option("--paper", "-p", help="58, 80 or custom.")]
WidthOpt = Annotated[int | None, typer.Option("--width", "-w", help="Custom dot width.")]
DitherOpt = Annotated[
    str,
    typer.Option(
        "--dither",
        "-d",
        help="bayer4, bayer8, atkinson, fs, halftone, mean or none.",
    ),
]
ScaleOpt = Annotated[str, typer.Option("--scale", help="fit, fill or stretch.")]
RotateOpt = Annotated[
    int, typer.Option("--rotate", help="0, 90, 180 or 270 degrees clockwise.")
]
MarginOpt = Annotated[int, typer.Option("--margin", help="Margin in dots on every side.")]
BorderOpt = Annotated[
    bool, typer.Option("--border", help="Draw a 1-dot frame around the image.")
]
GammaOpt = Annotated[float, typer.Option("--gamma", help="Tone curve; >1 darkens the print.")]
BrightnessOpt = Annotated[int, typer.Option("--brightness", help="-255..255.")]
ContrastOpt = Annotated[float, typer.Option("--contrast", help="0.1..4.0.")]
ThresholdOpt = Annotated[
    int, typer.Option("--threshold", help="0..255; 128 means auto for 'mean'.")
]
InvertOpt = Annotated[bool, typer.Option("--invert", help="Invert light and dark.")]
MaxHeightOpt = Annotated[int | None, typer.Option("--max-height", help="Height cap in dots.")]
SidecarOpt = Annotated[
    bool, typer.Option("--sidecar/--no-sidecar", help="Write a .json sidecar.")
]
PresetOpt = Annotated[
    str | None,
    typer.Option(
        "--preset",
        help="Start from a named preset; flags you type override it. See `tdots presets`.",
    ),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _options(
    *,
    paper: str,
    width: int | None,
    dither: str,
    scale: str,
    rotate: int,
    margin: int,
    border: bool,
    gamma: float,
    brightness: int,
    contrast: float,
    threshold: int,
    invert: bool,
    max_height: int | None,
    preset: str | None = None,
    ctx: typer.Context | None = None,
    render_width: int | None = None,
) -> ConvertOptions:
    values: dict[str, Any] = {
        "paper": paper,
        "dither": dither,
        "scale": scale,
        "gamma": gamma,
        "contrast": contrast,
        "threshold": threshold,
    }

    if preset:
        if preset not in PRESETS:
            raise InvalidOptionsError(
                f"Unknown preset {preset!r}.",
                hint="Available: " + ", ".join(sorted(PRESETS)),
            )
        for name, value in PRESETS[preset].items():
            if name not in values:
                continue
            # A flag typed on the command line beats the preset; a flag left at
            # its default does not. This is the only ordering that lets
            # `--preset photo-floyd --gamma 0.9` mean what it looks like.
            # Compared by name so this does not depend on where typer vendors
            # click's ParameterSource enum.
            source = ctx.get_parameter_source(name) if ctx is not None else None
            if source is not None and getattr(source, "name", "") == "COMMANDLINE":
                continue
            values[name] = value
        gamma = float(values["gamma"])
        contrast = float(values["contrast"])
        threshold = int(values["threshold"])
        paper = str(values["paper"])
        dither = str(values["dither"])
        scale = str(values["scale"])

    return ConvertOptions(
        paper=Paper.parse(paper),
        width_dots=width,
        dither=dither,  # type: ignore[arg-type]
        scale=scale,  # type: ignore[arg-type]
        rotate=rotate,
        margin=margin,
        border=border,
        gamma=gamma,
        brightness=brightness,
        contrast=contrast,
        threshold=threshold,
        auto_threshold=(threshold == 128),
        invert=invert,
        max_height_dots=max_height,
        render_width=render_width,
    )


def _export(
    result: ConversionResult,
    output: Path,
    fmt: OutputFormat,
    *,
    init: bool,
    feed: int,
    cut: bool,
    sidecar: bool,
    compress_level: int = 6,
    upscale: int = 1,
) -> Path:
    if fmt is OutputFormat.PNG:
        data = result.png_bytes(compress_level=compress_level, upscale=upscale)
    elif fmt is OutputFormat.BMP:
        data = result.bmp_bytes(upscale=upscale)
    elif fmt is OutputFormat.ESCPOS:
        data = result.escpos_bytes(init=init, feed_lines=feed, cut=cut)
    elif fmt is OutputFormat.TEXT:
        data = (result.half_blocks(max_width=result.width) + "\n").encode("utf-8")
    else:  # pragma: no cover - enum is exhaustive
        raise AssertionError(fmt)

    written = atomic_write(output, data)
    if sidecar:
        metadata = result.describe()
        metadata["format"] = fmt.value
        metadata["bytes"] = len(data)
        metadata["upscale"] = upscale
        metadata["pixel_width"] = result.width * upscale
        metadata["pixel_height"] = result.height * upscale
        if result.options.render_width is not None:
            metadata["screen_export"] = True
        metadata["escpos"] = {"init": init, "feed_lines": feed, "cut": cut}
        write_sidecar(written, metadata)
    return written


def _default_output(
    source: Path, options: ConvertOptions, fmt: OutputFormat, upscale: int = 1
) -> Path:
    if options.render_width is not None:
        stem = f"{source.stem}_{options.render_width}px_{options.dither.value}"
    else:
        stem = f"{source.stem}_{options.paper.value}_{options.dither.value}"
    if upscale != 1:
        stem += f"_x{upscale}"
    return source.with_name(stem + "." + fmt.suffix)


def _validate_upscale(requested: int | None, fmt: OutputFormat) -> None:
    """Upscale is a raster-file convenience; it must never touch printer bytes."""
    if requested != 1 and fmt in (OutputFormat.ESCPOS, OutputFormat.TEXT):
        raise InvalidOptionsError(
            "upscale only applies to png and bmp output.",
            hint=(
                "ESC/POS and text stay at the printer's dot grid. "
                "Use -f png or -f bmp to enlarge the file."
            ),
        )


def _render_requested(value: str) -> bool:
    """True unless the setting means 'use the printer width'."""
    return value.strip().lower() not in ("", "print", "paper", "none")


def _resolve_render_width(value: str, source_width: int) -> int | None:
    """Turn ``--render-width`` into a pixel width, or ``None`` for print mode."""
    text = value.strip().lower()
    if text in ("", "print", "paper", "none"):
        return None
    if text == "native":
        if not 8 <= source_width <= RENDER_WIDTH_MAX:
            raise InvalidOptionsError(
                f"native rendering needs a source 8 to {RENDER_WIDTH_MAX} px wide, "
                f"but this image is {source_width} px.",
                hint=f"Pass an explicit width, for example --render-width {RENDER_WIDTH_MAX}.",
            )
        return source_width
    try:
        width = int(text)
    except ValueError:
        raise InvalidOptionsError(
            "render-width must be 'native' or a whole number "
            f"from 8 to {RENDER_WIDTH_MAX}."
        ) from None
    if not 8 <= width <= RENDER_WIDTH_MAX:
        raise InvalidOptionsError(
            f"render-width must be between 8 and {RENDER_WIDTH_MAX}, got {width}."
        )
    return width


def _validate_render(value: str, fmt: OutputFormat) -> None:
    """Native rendering is a screen asset; printer bytes keep their dot grid."""
    if _render_requested(value) and fmt in (OutputFormat.ESCPOS, OutputFormat.TEXT):
        raise InvalidOptionsError(
            "render-width only applies to png and bmp output.",
            hint=(
                "ESC/POS and text must stay at 384/576 dots. "
                "Use -f png or -f bmp for a screen-sized export."
            ),
        )


def _summary(
    result: ConversionResult, target: Path, fmt: OutputFormat, upscale: int = 1
) -> Table:
    screen = result.options.render_width is not None
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("source", result.source)
    table.add_row("dots", f"{result.width} x {result.height} px")
    if upscale != 1:
        table.add_row(
            "export",
            f"{result.width * upscale} x {result.height * upscale} px ({upscale}x pixels)",
        )
    if screen:
        table.add_row("mode", "screen export (no paper mapping)")
    else:
        width_mm, height_mm = result.physical_size_mm()
        table.add_row("physical", f"{width_mm:.1f} x {height_mm:.1f} mm @ 203 dpi")
    table.add_row("ink", f"{result.ink_ratio * 100:.1f} %")
    table.add_row("raster", f"{result.raster_bytes:,} bytes ({result.row_bytes} bytes/row)")
    table.add_row("dither", result.options.dither.value)
    table.add_row("timing", f"{result.total_ms:.0f} ms")
    table.add_row("format", fmt.value)
    table.add_row("output", str(target))
    return table


def _fail(error: ThermalDotsError, code: int = 2) -> None:
    err_console.print(f"[bold red]![/] {error.message}")
    if error.hint:
        err_console.print(f"[dim]  hint: {error.hint}[/]")
    raise typer.Exit(code=code)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


@app.command("convert")
def convert_command(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Input image file."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path."),
    preset: PresetOpt = None,
    paper: PaperOpt = "58",
    width: WidthOpt = None,
    dither: DitherOpt = "bayer4",
    fmt: str = typer.Option("png", "--format", "-f", help="png, bmp, bin (ESC/POS) or txt."),
    scale: ScaleOpt = "fit",
    rotate: RotateOpt = 0,
    margin: MarginOpt = 0,
    border: BorderOpt = False,
    gamma: GammaOpt = 1.0,
    brightness: BrightnessOpt = 0,
    contrast: ContrastOpt = 1.0,
    threshold: ThresholdOpt = 128,
    invert: InvertOpt = False,
    max_height: MaxHeightOpt = None,
    init: bool = typer.Option(True, "--init/--no-init", help="ESC/POS: send ESC @ first."),
    feed: int = typer.Option(3, "--feed", help="ESC/POS: feed lines after the image."),
    cut: bool = typer.Option(False, "--cut", help="ESC/POS: send a full cut."),
    sidecar: SidecarOpt = True,
    compress_level: int = typer.Option(6, "--compress-level", help="PNG compression 0..9."),
    upscale: str = typer.Option(
        "1",
        "--upscale",
        help="PNG/BMP size: 1-16, or 'auto' to match the source width.",
    ),
    render_width: str = typer.Option(
        "print",
        "--render-width",
        help="Screen export: 'native' for the source width, or 8-8192 px.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Convert one image."""
    try:
        if not 0 <= compress_level <= 9:
            raise InvalidOptionsError("compress-level must be between 0 and 9.")
        output_format = OutputFormat.parse(fmt)
        requested = parse_upscale(upscale)
        _validate_upscale(requested, output_format)
        _validate_render(render_width, output_format)
        source_width = int(probe(source)["width"])
        resolved_render = _resolve_render_width(render_width, source_width)
        options = _options(
            paper=paper,
            width=width,
            dither=dither,
            scale=scale,
            rotate=rotate,
            margin=margin,
            border=border,
            gamma=gamma,
            brightness=brightness,
            contrast=contrast,
            threshold=threshold,
            invert=invert,
            max_height=max_height,
            preset=preset,
            ctx=ctx,
            render_width=resolved_render,
        )
        factor = resolve_upscale(
            requested, options.resolved_width(), source_width if requested is None else 0
        )
        target = output or _default_output(source, options, output_format, factor)
        result = run_convert(source, options)
        written = _export(
            result,
            target,
            output_format,
            init=init,
            feed=feed,
            cut=cut,
            sidecar=sidecar,
            compress_level=compress_level,
            upscale=factor,
        )
    except ThermalDotsError as error:
        _fail(error)

    if as_json:
        payload = result.describe()
        payload["output"] = str(written)
        payload["upscale"] = factor
        payload["pixel_width"] = result.width * factor
        payload["pixel_height"] = result.height * factor
        if result.options.render_width is not None:
            payload["screen_export"] = True
        console.print_json(json.dumps(payload))
        return

    console.print(
        Panel(
            _summary(result, written, output_format, factor),
            title="thermal-dots",
            border_style="green",
        )
    )


@app.command("batch")
def batch_command(
    ctx: typer.Context,
    source_dir: Path = typer.Argument(..., help="Folder of images."),
    out_dir: Path = typer.Option(Path("out"), "--out", "-o", help="Destination folder."),
    preset: PresetOpt = None,
    paper: PaperOpt = "58",
    width: WidthOpt = None,
    dither: DitherOpt = "bayer4",
    fmt: str = typer.Option("png", "--format", "-f"),
    scale: ScaleOpt = "fit",
    rotate: RotateOpt = 0,
    margin: MarginOpt = 0,
    border: BorderOpt = False,
    gamma: GammaOpt = 1.0,
    brightness: BrightnessOpt = 0,
    contrast: ContrastOpt = 1.0,
    threshold: ThresholdOpt = 128,
    invert: InvertOpt = False,
    max_height: MaxHeightOpt = None,
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Walk sub-folders."),
    sidecar: SidecarOpt = True,
    upscale: str = typer.Option(
        "1",
        "--upscale",
        help="PNG/BMP size: 1-16, or 'auto' to match each source width.",
    ),
    render_width: str = typer.Option(
        "print",
        "--render-width",
        help="Screen export: 'native' for each source width, or 8-8192 px.",
    ),
) -> None:
    """Convert every image in a folder; one bad file never aborts the run."""
    if not source_dir.is_dir():
        _fail(ThermalDotsError(f"{source_dir} is not a folder."))

    pattern = "**/*" if recursive else "*"
    files = sorted(
        path
        for path in source_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not files:
        _fail(ThermalDotsError(f"No images found in {source_dir}."))

    try:
        native_render = render_width.strip().lower() == "native"
        fixed_render = (
            None if native_render else _resolve_render_width(render_width, 0)
        )
        options = _options(
            paper=paper,
            width=width,
            dither=dither,
            scale=scale,
            rotate=rotate,
            margin=margin,
            border=border,
            gamma=gamma,
            brightness=brightness,
            contrast=contrast,
            threshold=threshold,
            invert=invert,
            max_height=max_height,
            preset=preset,
            ctx=ctx,
            render_width=fixed_render,
        )
        output_format = OutputFormat.parse(fmt)
        requested = parse_upscale(upscale)
        _validate_upscale(requested, output_format)
        _validate_render(render_width, output_format)
    except ThermalDotsError as error:
        _fail(error)

    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[Path, str]] = []
    started = time.perf_counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("converting", total=len(files))
        for path in files:
            progress.update(task, description=f"[cyan]{path.name}")
            try:
                source_width = (
                    int(probe(path)["width"])
                    if native_render or requested is None
                    else 0
                )
                file_options = options
                if native_render:
                    file_options = options.replace(
                        render_width=_resolve_render_width("native", source_width)
                    )
                result = run_convert(path, file_options)
                factor = resolve_upscale(requested, result.width, source_width)
                label = (
                    f"{file_options.render_width}px"
                    if file_options.render_width is not None
                    else options.paper.value
                )
                name = path.stem + "_" + label
                if factor != 1:
                    name += f"_x{factor}"
                _export(
                    result,
                    out_dir / (name + "." + output_format.suffix),
                    output_format,
                    init=True,
                    feed=3,
                    cut=False,
                    sidecar=sidecar,
                    upscale=factor,
                )
            except ThermalDotsError as error:
                failures.append((path, error.message))
            except Exception as error:  # pragma: no cover - defensive
                failures.append((path, f"{type(error).__name__}: {error}"))
            progress.advance(task)

    elapsed = time.perf_counter() - started
    ok = len(files) - len(failures)
    console.print(
        f"[green]ok[/] {ok}/{len(files)} images in {elapsed:.1f}s -> [bold]{out_dir}[/]"
    )
    if failures:
        console.print(f"[red]failed[/] {len(failures)}:")
        for path, message in failures:
            console.print(f"  [red]![/] {path.name}: {message}")
        raise typer.Exit(code=1)


@app.command("preview")
def preview_command(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Input image file."),
    preset: PresetOpt = None,
    paper: PaperOpt = "58",
    width: WidthOpt = None,
    dither: DitherOpt = "bayer4",
    scale: ScaleOpt = "fit",
    rotate: RotateOpt = 0,
    margin: MarginOpt = 0,
    border: BorderOpt = False,
    gamma: GammaOpt = 1.0,
    brightness: BrightnessOpt = 0,
    contrast: ContrastOpt = 1.0,
    threshold: ThresholdOpt = 128,
    invert: InvertOpt = False,
    max_height: MaxHeightOpt = None,
    columns: int = typer.Option(48, "--columns", "-c", help="Preview width in characters."),
    render_width: str = typer.Option(
        "print",
        "--render-width",
        help="Screen preview: 'native' for the source width, or 8-8192 px.",
    ),
) -> None:
    """Render an ASCII/Unicode preview without writing a file.

    Accepts the same tone and geometry options as `convert`, so you can tune a
    photo in the terminal and then repeat the exact flags on the real export.
    """
    try:
        if columns < 1:
            raise InvalidOptionsError("columns must be at least 1.")
        resolved_render = _resolve_render_width(
            render_width, int(probe(source)["width"])
        )
        options = _options(
            paper=paper,
            width=width,
            dither=dither,
            scale=scale,
            rotate=rotate,
            margin=margin,
            border=border,
            gamma=gamma,
            brightness=brightness,
            contrast=contrast,
            threshold=threshold,
            invert=invert,
            max_height=max_height,
            preset=preset,
            ctx=ctx,
            render_width=resolved_render,
        )
        result = run_convert(source, options)
    except ThermalDotsError as error:
        _fail(error)

    console.print(
        f"[dim]{result.width}x{result.height} dots, ink {result.ink_ratio * 100:.1f}%, "
        f"{result.total_ms:.0f} ms[/]"
    )
    console.print("[green]" + result.half_blocks(max_width=columns) + "[/]")


@app.command("presets")
def presets_command() -> None:
    """List the built-in presets."""
    table = Table(title="presets")
    table.add_column("name", style="cyan")
    table.add_column("paper")
    table.add_column("dither")
    table.add_column("gamma")
    table.add_column("contrast")
    for name, data in PRESETS.items():
        table.add_row(
            name,
            str(data.get("paper")),
            str(data.get("dither")),
            str(data.get("gamma")),
            str(data.get("contrast")),
        )
    console.print(table)


@app.command("doctor")
def doctor_command() -> None:
    """Print environment diagnostics and paper capabilities."""
    import importlib.util

    import numpy
    from PIL import Image as PILImage
    from PIL import __version__ as pillow_version

    table = Table(title="environment", show_header=False, box=None)
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("thermal-dots", __version__)
    table.add_row("python", sys.version.split()[0])
    table.add_row("pillow", pillow_version)
    table.add_row("numpy", numpy.__version__)
    table.add_row("pywebview", "installed" if importlib.util.find_spec("webview") else "missing (GUI disabled)")
    table.add_row("webview2", "present" if _webview2_installed() else "missing (GUI cannot start)")
    console.print(table)

    papers = Table(title="paper profiles")
    papers.add_column("paper", style="cyan")
    papers.add_column("dots", justify="right")
    papers.add_column("bytes/row", justify="right")
    papers.add_column("printable mm", justify="right")
    for entry in list_papers():
        papers.add_row(
            entry["label"],
            str(entry["width_dots"]),
            str(entry["row_bytes"]),
            str(entry["printable_mm"]),
        )
    console.print(papers)

    extensions = ", ".join(sorted(PILImage.registered_extensions())) or "n/a"
    console.print(f"[dim]decoders: {extensions}[/]")


@app.command("gui")
def gui_command(
    debug: bool = typer.Option(False, "--debug", help="Open devtools and verbose logging."),
    width: int = typer.Option(1180, "--width"),
    height: int = typer.Option(820, "--height"),
) -> None:
    """Launch the retro desktop UI."""
    try:
        from .ui.app import main as ui_main
    except ImportError as error:
        _fail(
            ThermalDotsError(
                f"GUI dependencies are not installed ({error}).",
                hint="Install them with: pip install \"thermal-dots[gui]\"",
            )
        )
        return
    ui_main(debug=debug, width=width, height=height)


@app.command("info")
def info_command(source: Path = typer.Argument(..., help="Input image file.")) -> None:
    """Show metadata for an image without converting it."""
    try:
        data = probe(source)
    except ThermalDotsError as error:
        _fail(error)
    console.print_json(json.dumps(data, indent=2))


@app.callback(invoke_without_command=True)
def _root(
    version: bool = typer.Option(False, "--version", help="Show the version and exit."),
) -> None:
    if version:
        console.print(f"thermal-dots {__version__}")
        raise typer.Exit()


def _webview2_installed() -> bool:
    try:
        import winreg

        keys = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        )
        for root, path in keys:
            try:
                with winreg.OpenKey(root, path) as key:
                    winreg.QueryValueEx(key, "pv")
                    return True
            except OSError:
                continue
    except ImportError:  # pragma: no cover - non-Windows
        pass
    return Path(r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application").is_dir()


def _is_frozen() -> bool:
    """True inside a compiled bundle (Nuitka/PyInstaller), False for a checkout."""
    return bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()


def _has_console() -> bool:
    """True when the process owns a console window (launched from a terminal)."""
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:  # pragma: no cover - non-Windows, or no ctypes
        stream = sys.stdout
        return bool(stream is not None and stream.isatty())


def _double_clicked() -> bool:
    """A frozen exe with no arguments and no console was started from Explorer."""
    return _is_frozen() and len(sys.argv) == 1 and not _has_console()


def main() -> None:
    """Console-script entry point, and the frozen exe's entry point.

    Explorer cannot pass arguments to a double-clicked exe, and this build has no
    console window to print help into.  In that one case the GUI is the only
    sensible action; a terminal launch still gets the usual CLI behaviour.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # redirected to a stream without a buffer
            continue
        with contextlib.suppress(Exception):
            reconfigure(encoding="utf-8", errors="replace")
    if _double_clicked():
        from .ui.app import main as ui_main

        ui_main()
        return
    app()


if __name__ == "__main__":
    main()
