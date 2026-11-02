"""Retro desktop UI (pywebview + WebView2).

The Python side is deliberately thin: it owns the image handles, runs the same
pipeline the CLI uses, and exposes it through a small JSON-safe API.  All
rendering, layout and keyboard handling live in ``web/``.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from ..errors import InvalidOptionsError, ThermalDotsError
from ..exporters import atomic_write, write_sidecar
from ..models import ConvertOptions, OutputFormat, parse_upscale, resolve_upscale
from ..pipeline import convert, probe
from ..profiles import PRESETS, list_papers

__all__ = ["Api", "main"]

LOGGER = logging.getLogger("thermaldots.ui")
ASSETS = Path(__file__).resolve().parent / "web"
APP_TITLE = "THERMAL//DOTS"

# Raw uploads are kept in memory so previews can re-run the pipeline without a
# round-trip through the webview.  A handful is plenty; anything older is
# dropped and the UI reports the handle as expired.
MAX_SOURCES = 8


def _log_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".thermal-dots"))
    folder = base / "ThermalDots" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "thermal-dots.log"


def _configure_logging(debug: bool) -> None:
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.DEBUG if debug else logging.INFO)
    try:
        handler: logging.Handler = RotatingFileHandler(
            _log_file(), maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
    except OSError:  # read-only profile folder - keep the app usable
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    LOGGER.addHandler(handler)


def _error_payload(error: ThermalDotsError) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, **error.to_dict()}
    return payload


def _decode_data_url(data_url: str) -> bytes:
    payload = data_url.split(",", 1)
    if len(payload) != 2:
        raise ValueError("expected a data URL")
    try:
        return base64.b64decode(payload[1], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"invalid base64 payload: {error}") from error


class Api:
    """The object exposed to JavaScript as ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._sources: dict[str, bytes] = {}
        self._names: dict[str, str] = {}
        self._window: Any = None

    # -- plumbing ---------------------------------------------------------- #

    def attach(self, window: Any) -> None:
        self._window = window

    def _remember(self, handle: str, raw: bytes, name: str) -> None:
        self._sources[handle] = raw
        self._names[handle] = name
        while len(self._sources) > MAX_SOURCES:
            oldest = next(iter(self._sources))
            if oldest == handle:  # pragma: no cover - only with MAX_SOURCES=0
                break
            del self._sources[oldest]
            self._names.pop(oldest, None)

    def bootstrap(self) -> dict[str, Any]:
        from .. import __version__

        return {
            "ok": True,
            "version": __version__,
            "papers": list_papers(),
            "presets": PRESETS,
            "formats": [fmt.value for fmt in OutputFormat],
            "dithers": [
                "bayer4",
                "bayer8",
                "atkinson",
                "fs",
                "halftone",
                "mean",
                "none",
            ],
            "log_file": str(_log_file()),
        }

    # -- image handling ---------------------------------------------------- #

    def load_image(self, data_url: str, name: str) -> dict[str, Any]:
        try:
            raw = _decode_data_url(data_url)
            handle = uuid.uuid4().hex
            info = probe(raw)
            self._remember(handle, raw, name or info["name"])
            LOGGER.info("loaded %s (%s, %sx%s)", name, info["format"], info["width"], info["height"])
            return {
                "ok": True,
                "handle": handle,
                "name": self._names[handle],
                "bytes": len(raw),
                "source": info,
            }
        except ThermalDotsError as error:
            LOGGER.warning("load_image failed: %s", error)
            return _error_payload(error)
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.exception("load_image crashed")
            return {"ok": False, "message": str(error), "hint": None}

    def preview(self, handle: str, options: dict[str, Any]) -> dict[str, Any]:
        try:
            data = self._sources[handle]
            opts = ConvertOptions.from_dict(options)
            result = convert(data, opts, cache_key=handle)
            png = result.png_bytes(compress_level=3)
            width_mm, height_mm = result.physical_size_mm()
            screen = opts.render_width is not None
            return {
                "ok": True,
                "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                "width": result.width,
                "height": result.height,
                "row_bytes": result.row_bytes,
                "raster_bytes": result.raster_bytes,
                "ink_ratio": round(result.ink_ratio, 4),
                "ms": round(result.total_ms, 1),
                "mm": [round(width_mm, 1), round(height_mm, 1)],
                "print_seconds": result.estimated_print_seconds(result.raster_bytes),
                "screen": screen,
            }
        except ThermalDotsError as error:
            return _error_payload(error)
        except KeyError:
            return {"ok": False, "message": "Image handle expired.", "hint": "Load the image again."}
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.exception("preview crashed")
            return {"ok": False, "message": str(error), "hint": None}

    def export(
        self,
        handle: str,
        options: dict[str, Any],
        fmt: str,
        sidecar: bool = True,
        escpos: dict[str, Any] | None = None,
        upscale: str | int = 1,
    ) -> dict[str, Any]:
        try:
            data = self._sources[handle]
            opts = ConvertOptions.from_dict(options)
            output_format = OutputFormat.parse(fmt)
            requested = parse_upscale(upscale)
            if requested != 1 and output_format not in (
                OutputFormat.PNG,
                OutputFormat.BMP,
            ):
                raise InvalidOptionsError(
                    "upscale only applies to png and bmp output.",
                    hint="ESC/POS and text stay at the printer's dot grid.",
                )
            if opts.render_width is not None and output_format not in (
                OutputFormat.PNG,
                OutputFormat.BMP,
            ):
                raise InvalidOptionsError(
                    "render-width only applies to png and bmp output.",
                    hint="ESC/POS and text must stay at 384/576 dots.",
                )
            result = convert(data, opts, cache_key=handle)
            source_width = int(probe(data)["width"]) if requested is None else 0
            factor = resolve_upscale(requested, result.width, source_width)
        except ThermalDotsError as error:
            return _error_payload(error)
        except KeyError:
            return {"ok": False, "message": "Image handle expired.", "hint": "Load the image again."}
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.exception("export prepare crashed")
            return {"ok": False, "message": str(error), "hint": None}

        suffix = "." + output_format.suffix
        if opts.render_width is not None:
            suggested = (
                f"{Path(self._names.get(handle, 'image')).stem}_"
                f"{opts.render_width}px_{opts.dither.value}{suffix}"
            )
        else:
            suggested = (
                f"{Path(self._names.get(handle, 'image')).stem}_"
                f"{opts.paper.value}_{opts.dither.value}{suffix}"
            )

        try:
            target = self._ask_save_path(suggested, output_format)
        except Exception:  # pragma: no cover - dialog failure
            LOGGER.exception("save dialog failed")
            target = None

        if target is None:
            return {"ok": False, "cancelled": True}

        settings = escpos or {}
        try:
            if output_format is OutputFormat.PNG:
                payload = result.png_bytes(compress_level=6, upscale=factor)
            elif output_format is OutputFormat.BMP:
                payload = result.bmp_bytes(upscale=factor)
            elif output_format is OutputFormat.ESCPOS:
                payload = result.escpos_bytes(
                    init=bool(settings.get("init", True)),
                    feed_lines=int(settings.get("feed", 3)),
                    cut=bool(settings.get("cut", False)),
                )
            else:
                payload = (result.half_blocks(max_width=result.width) + "\n").encode("utf-8")

            written = atomic_write(target, payload)
            if sidecar:
                metadata = result.describe()
                metadata["format"] = output_format.value
                metadata["bytes"] = len(payload)
                metadata["upscale"] = factor
                metadata["pixel_width"] = result.width * factor
                metadata["pixel_height"] = result.height * factor
                if opts.render_width is not None:
                    metadata["screen_export"] = True
                write_sidecar(written, metadata)
        except ThermalDotsError as error:
            LOGGER.warning("write failed: %s", error)
            return _error_payload(error)
        except OSError as error:
            LOGGER.exception("write failed")
            return {
                "ok": False,
                "error": type(error).__name__,
                "message": f"Could not write {target}.",
                "hint": "Is the file open in another application?",
            }

        LOGGER.info("exported %s (%s)", written, output_format.value)
        return {
            "ok": True,
            "path": str(written),
            "bytes": len(payload),
            "format": output_format.value,
            "upscale": factor,
            "pixel_width": result.width * factor,
            "pixel_height": result.height * factor,
            "screen": opts.render_width is not None,
        }

    def reveal_logs(self) -> dict[str, Any]:
        path = _log_file()
        try:
            if sys.platform == "win32":
                os.startfile(path.parent)
            return {"ok": True, "path": str(path)}
        except OSError as error:
            return {"ok": False, "message": str(error)}

    def _ask_save_path(self, suggested: str, output_format: OutputFormat) -> str | None:
        if self._window is None:
            return None
        import webview

        types = {
            OutputFormat.PNG: ("PNG image (*.png)",),
            OutputFormat.BMP: ("Bitmap (*.bmp)",),
            OutputFormat.ESCPOS: ("ESC/POS raw (*.bin)",),
            OutputFormat.TEXT: ("Text (*.txt)",),
        }[output_format]
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested,
            file_types=types,
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)


def main(*, debug: bool = False, width: int = 1180, height: int = 820) -> None:
    _configure_logging(debug)
    try:
        import webview
    except ImportError as error:  # pragma: no cover - optional dependency
        raise SystemExit(
            "pywebview is not installed. Run: pip install \"thermal-dots[gui]\""
        ) from error

    api = Api()
    window = webview.create_window(
        APP_TITLE,
        str(ASSETS / "index.html"),
        js_api=api,
        width=width,
        height=height,
        min_size=(980, 680),
        background_color="#040706",
        text_select=True,
    )
    api.attach(window)

    try:
        # private_mode keeps every launch on a clean WebView2 profile. Without
        # it, WebView2 caches the HTML/JS/CSS and an update can silently serve
        # last version's assets next to this version's.
        webview.start(debug=debug, private_mode=True)
    except Exception as error:  # pragma: no cover - missing WebView2 runtime
        LOGGER.exception("webview failed to start")
        raise SystemExit(
            "Could not start the webview.\n"
            f"  {error}\n"
            "Install the Microsoft Edge WebView2 runtime:\n"
            "  https://developer.microsoft.com/microsoft-edge/webview2/"
        ) from error
