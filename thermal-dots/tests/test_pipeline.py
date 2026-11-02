from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import thermaldots.pipeline as pipeline_module
from thermaldots.dither import atkinson
from thermaldots.errors import (
    ConversionCancelled,
    ImageTooLargeError,
    InvalidOptionsError,
    SourceNotFoundError,
    UnsupportedImageError,
)
from thermaldots.models import ConvertOptions, DitherMode, Paper, ScaleMode
from thermaldots.pipeline import CancellationToken, clear_cache, convert, probe


@pytest.mark.parametrize("dither", list(DitherMode))
def test_every_dither_mode_produces_invariants(gradient_jpeg, dither: DitherMode) -> None:
    result = convert(gradient_jpeg, ConvertOptions(dither=dither))
    assert result.ink.dtype == bool
    assert result.ink.ndim == 2
    assert result.width == 384
    assert result.height > 0
    assert result.raster_bytes == result.row_bytes * result.height
    assert result.row_bytes == 48


@pytest.mark.parametrize(("paper", "expected"), [(Paper.MM58, 384), (Paper.MM80, 576)])
def test_paper_widths(gradient_png, paper: Paper, expected: int) -> None:
    result = convert(gradient_png, ConvertOptions(paper=paper))
    assert result.width == expected
    assert result.row_bytes == (expected + 7) // 8


def test_aspect_ratio_is_preserved(gradient_png) -> None:
    result = convert(gradient_png, ConvertOptions())
    # 640x480 source -> 384 wide -> 288 high
    assert result.height == 288


def test_rotate_swaps_aspect(gradient_png) -> None:
    result = convert(gradient_png, ConvertOptions(rotate=90))
    assert result.width == 384
    assert result.height == 512


def test_tiny_image_is_upscaled(tiny_png) -> None:
    result = convert(tiny_png)
    assert result.width == 384
    assert result.height == 384
    assert result.ink.all()  # a single black pixel fills the page


def test_transparent_area_becomes_paper(alpha_png) -> None:
    result = convert(alpha_png, ConvertOptions(dither=DitherMode.NONE))
    assert not result.ink[0, 0]
    assert not result.ink[-1, -1]
    assert result.ink[result.height // 2, result.width // 2]


def test_scale_fill_crops_to_max_height(gradient_png) -> None:
    result = convert(gradient_png, ConvertOptions(scale=ScaleMode.FILL, max_height_dots=200))
    assert result.height == 200
    assert result.width == 384


@pytest.mark.parametrize("size", [(100, 333), (333, 100), (101, 37), (999, 7), (7, 999)])
def test_scale_fill_is_exact_without_black_edges(size: tuple[int, int]) -> None:
    """FILL must return the exact box, with no black padding from an over-crop."""
    result = convert(
        Image.new("L", size, 255),
        ConvertOptions(scale=ScaleMode.FILL, max_height_dots=120, dither=DitherMode.NONE),
    )
    assert (result.width, result.height) == (384, 120)
    assert not result.ink.any()


def test_scale_stretch_with_max_height_ignores_aspect() -> None:
    result = convert(
        Image.new("L", (50, 200), 255),
        ConvertOptions(scale=ScaleMode.STRETCH, max_height_dots=100, dither=DitherMode.NONE),
    )
    assert (result.width, result.height) == (384, 100)


def test_margin_and_border() -> None:
    result = convert(
        np.zeros((10, 10), dtype=np.uint8),
        ConvertOptions(margin=4, border=True, dither=DitherMode.NONE),
    )
    inner = 384 - 2 * 4 - 2  # border eats one dot on each side
    assert result.width == 384
    assert result.height == inner + 2 * 4 + 2
    assert not result.ink[0, 0]  # margin is paper
    assert result.ink[4, 4]  # frame starts here


def test_invert_flips_ink() -> None:
    rng = np.random.default_rng(3)
    source = rng.integers(0, 256, size=(64, 384), dtype=np.uint8)
    source[source == 128] = 127  # avoid the tie case at the threshold
    base = ConvertOptions(dither=DitherMode.MEAN, threshold=128, auto_threshold=False)
    normal = convert(source, base)
    inverted = convert(source, base.replace(invert=True))
    assert np.array_equal(normal.ink, ~inverted.ink)


def test_gamma_darkens() -> None:
    source = np.full((32, 32), 170, dtype=np.uint8)
    base = ConvertOptions(dither=DitherMode.MEAN, threshold=128, auto_threshold=False)
    light = convert(source, base)
    dark = convert(source, base.replace(gamma=2.0))
    assert dark.ink.mean() > light.ink.mean()


def test_cache_reuses_decoded_image(gradient_jpeg) -> None:
    clear_cache()
    convert(gradient_jpeg, ConvertOptions(dither=DitherMode.BAYER4))
    convert(gradient_jpeg, ConvertOptions(dither=DitherMode.ATKINSON, gamma=1.4))
    assert len(pipeline_module._cache) == 1


def test_cancel_token_stops_conversion(gradient_jpeg) -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ConversionCancelled):
        convert(gradient_jpeg, cancel=token)


def test_progress_events_are_emitted(gradient_png) -> None:
    events = []
    convert(gradient_png, progress=events.append)
    assert [event.stage for event in events][-1] == "done"
    assert events[-1].fraction == pytest.approx(4 / 5)


def test_missing_file_raises() -> None:
    with pytest.raises(SourceNotFoundError):
        convert("definitely-not-here.png")


def test_directory_raises(tmp_path) -> None:
    with pytest.raises(SourceNotFoundError):
        convert(tmp_path)


def test_corrupt_file_raises(corrupt_file) -> None:
    with pytest.raises(UnsupportedImageError):
        convert(corrupt_file)


def test_decompression_guard() -> None:
    with pytest.raises(ImageTooLargeError):
        convert(np.zeros((200, 200), dtype=np.uint8), ConvertOptions(max_source_pixels=1000))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_dots": 4},
        {"rotate": 45},
        {"gamma": 0.0},
        {"contrast": 9.0},
        {"threshold": 300},
        {"margin": 400},
        {"paper": Paper.CUSTOM},
    ],
)
def test_invalid_options(kwargs) -> None:
    with pytest.raises(InvalidOptionsError):
        ConvertOptions(**kwargs)


def test_mismatched_width_and_paper() -> None:
    with pytest.raises(InvalidOptionsError):
        ConvertOptions(paper=Paper.MM58, width_dots=576)


def test_custom_paper_requires_width() -> None:
    assert ConvertOptions(paper=Paper.CUSTOM, width_dots=512).resolved_width() == 512


def test_probe_does_not_decode(gradient_jpeg) -> None:
    info = probe(gradient_jpeg)
    assert info["width"] == 640
    assert info["format"] == "JPEG"


def test_physical_size(gradient_png) -> None:
    result = convert(gradient_png)
    width_mm, height_mm = result.physical_size_mm()
    assert width_mm == pytest.approx(48.0, abs=0.2)
    assert height_mm > 30


def test_total_ms_is_not_double_counted(gradient_png) -> None:
    result = convert(gradient_png)
    stages = {name: value for name, value in result.timings.items() if name != "total"}
    assert result.total_ms == pytest.approx(result.timings["total"])
    assert result.total_ms == pytest.approx(sum(stages.values()), abs=1.0)
    assert result.total_ms > 0


def test_describe_rounds_timings(gradient_png) -> None:
    described = convert(gradient_png).describe()
    assert set(described["timings_ms"]) == {"decode", "tone", "dither", "total"}
    assert described["timings_ms"]["total"] > 0


def test_atkinson_reference_matches_dither_module() -> None:
    rng = np.random.default_rng(11)
    gray = rng.integers(0, 256, size=(64, 384), dtype=np.uint8)
    direct = atkinson(gray)
    via_pipeline = convert(gray, ConvertOptions(dither=DitherMode.ATKINSON))
    assert via_pipeline.width == 384
    assert np.array_equal(direct, via_pipeline.ink)

def test_render_width_wins_over_paper_and_round_trips(gradient_jpeg) -> None:
    options = ConvertOptions(paper=Paper.MM58, render_width=1000)
    assert options.resolved_width() == 1000
    result = convert(gradient_jpeg, options)
    assert result.width == 1000

    restored = ConvertOptions.from_dict(options.to_dict())
    assert restored.render_width == 1000
    assert restored.resolved_width() == 1000


@pytest.mark.parametrize("value", [7, 8193])
def test_render_width_range_is_validated(value: int) -> None:
    with pytest.raises(InvalidOptionsError):
        ConvertOptions(render_width=value)
