"""Decode corpus: every image mode a user can realistically drop in.

Mode handling is the classic source of "the app crashes on my file" reports, and
each of these crashes differently: palette images need ``convert("RGBA")`` to
respect transparency, 16-bit grayscale overflows a naive cast, CMYK inverts,
EXIF orientation silently rotates portraits.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from thermaldots.models import ConvertOptions, DitherMode, Paper
from thermaldots.pipeline import convert, probe

SIZE = (120, 90)


def _draw(image: Image.Image, fill: object) -> Image.Image:
    # One solid block on white: every mode then has an unambiguous
    # black region (top-left) and an unambiguous white one (bottom-right).
    ImageDraw.Draw(image).rectangle((0, 0, 59, 44), fill=fill)
    return image


@pytest.fixture()
def modes() -> dict[str, Image.Image]:
    """One representative image per Pillow mode."""
    images: dict[str, Image.Image] = {}

    images["1"] = _draw(Image.new("1", SIZE, 1), 0)
    images["L"] = _draw(Image.new("L", SIZE, 255), 0)
    images["LA"] = _draw(Image.new("LA", SIZE, (255, 255)), (0, 255))
    images["RGB"] = _draw(Image.new("RGB", SIZE, (255, 255, 255)), (0, 0, 0))
    images["RGBA"] = _draw(Image.new("RGBA", SIZE, (255, 255, 255, 255)), (0, 0, 0, 255))
    images["CMYK"] = _draw(Image.new("CMYK", SIZE, (0, 0, 0, 0)), (0, 0, 0, 255))
    images["I;16"] = _draw(Image.new("I;16", SIZE, 65535), 0)
    images["I"] = _draw(Image.new("I", SIZE, 255), 0)
    images["F"] = _draw(Image.new("F", SIZE, 1.0), 0.0)

    palette = Image.new("P", SIZE, 0)
    palette.putpalette([255, 255, 255] + [0, 0, 0] + [0, 0, 0] * 254)
    _draw(palette, 1)
    images["P"] = palette

    transparent = images["P"].copy()
    # Index 0 is the white background; make it transparent so the black block
    # (index 1) stays opaque - the realistic "logo on transparent PNG" case.
    transparent.info["transparency"] = 0
    images["P+transparency"] = transparent
    return images


@pytest.mark.parametrize("mode", ["1", "L", "LA", "RGB", "RGBA", "CMYK", "I;16", "I", "F", "P", "P+transparency"])
def test_mode_converts_to_exact_width(modes: dict[str, Image.Image], mode: str) -> None:
    image = modes[mode]
    assert image.mode == mode.split("+")[0]

    result = convert(image, ConvertOptions(dither=DitherMode.NONE, scale="stretch"))

    assert result.width == 384
    assert result.height > 0
    assert result.ink.dtype == bool
    assert result.row_bytes == 48
    assert 0.0 <= result.ink_ratio <= 1.0


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "CMYK", "I;16", "P+transparency"])
def test_black_shapes_are_inked(modes: dict[str, Image.Image], mode: str) -> None:
    result = convert(
        modes[mode],
        ConvertOptions(dither=DitherMode.NONE, threshold=128, auto_threshold=False, scale="stretch"),
    )
    # Top-left quadrant is the black shape, bottom-right the white one.
    h, w = result.ink.shape
    assert result.ink[: h // 3, : w // 3].mean() > 0.9
    assert result.ink[-h // 3 :, -w // 3 :].mean() < 0.1


def test_palette_transparency_prints_as_paper() -> None:
    image = Image.new("P", (64, 64), 0)
    image.putpalette([255, 255, 255] + [0, 0, 0] + [0, 0, 0] * 254)
    image.info["transparency"] = 0
    ImageDraw.Draw(image).rectangle((16, 16, 47, 47), fill=1)

    result = convert(image, ConvertOptions(dither=DitherMode.NONE))
    assert not result.ink[2, 2]  # transparent -> paper
    assert result.ink[result.height // 2, result.width // 2]


def test_sixteen_bit_gradient_is_not_clipped() -> None:
    ramp = np.linspace(0, 65535, 256, dtype=np.uint16)[None, :].repeat(32, axis=0)
    source = Image.fromarray(ramp)
    assert source.mode.startswith("I;16")
    result = convert(source, ConvertOptions(dither=DitherMode.NONE))
    # Left edge black, right edge white: a naive uint8 cast would clip to all-white.
    assert result.ink[:, :20].mean() > 0.9
    assert result.ink[:, -20:].mean() < 0.1


def test_exif_orientation_is_applied() -> None:
    portrait = Image.new("RGB", (40, 80), (255, 255, 255))
    ImageDraw.Draw(portrait).rectangle((0, 0, 39, 39), fill=(0, 0, 0))
    # Orientation 6 = rotate 90 CW on display, so stored 40x80 shows as 80x40.
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    portrait.save(buffer, format="JPEG", exif=exif)

    result = convert(buffer.getvalue(), ConvertOptions(dither=DitherMode.NONE))
    width_mm, _ = result.physical_size_mm()
    assert width_mm == pytest.approx(48.0, abs=0.3)
    # A landscape photo is shorter than it is wide after rotation.
    assert result.height < result.width


def test_one_by_one_pixel_is_supported() -> None:
    result = convert(Image.new("RGB", (1, 1), (0, 0, 0)))
    assert result.width == 384
    assert result.ink.all()


def test_extreme_aspect_ratio() -> None:
    result = convert(Image.new("L", (2000, 3), 0), ConvertOptions(paper=Paper.MM80))
    assert result.width == 576
    assert result.height == 1


def test_probe_reports_modes(gradient_png) -> None:
    info = probe(gradient_png)
    assert info["mode"] == "RGB"
    assert info["format"] == "PNG"
