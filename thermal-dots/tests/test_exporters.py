from __future__ import annotations

import io
import os
import tempfile

import numpy as np
import pytest
from PIL import Image

from thermaldots.errors import OutputError, OutputInUseError
from thermaldots.exporters import (
    atomic_write,
    bmp_bytes,
    escpos_bytes,
    half_block_text,
    png_bytes,
    write_sidecar,
)
from thermaldots.models import ConvertOptions, DitherMode
from thermaldots.pipeline import convert


@pytest.fixture()
def ink() -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 2, size=(120, 384)).astype(bool)


def test_png_is_one_bit(ink: np.ndarray) -> None:
    image = Image.open(io.BytesIO(png_bytes(ink)))
    assert image.mode == "1"
    assert image.size == (384, 120)
    assert np.array_equal(np.asarray(image) == 0, ink)


def test_bmp_is_one_bit(ink: np.ndarray) -> None:
    image = Image.open(io.BytesIO(bmp_bytes(ink)))
    assert image.mode == "1"
    assert image.size == (384, 120)


def test_escpos_header_and_length(ink: np.ndarray) -> None:
    payload = escpos_bytes(ink, init=True, feed_lines=3, cut=False)
    assert payload[:2] == b"\x1b@"
    assert payload[2:6] == b"\x1dv0\x00"
    assert payload[6:8] == (48).to_bytes(2, "little")
    assert payload[8:10] == (120).to_bytes(2, "little")
    assert len(payload) == 2 + 8 + 48 * 120 + 3


def test_escpos_fragments() -> None:
    ink = np.zeros((2000, 384), dtype=bool)
    payload = escpos_bytes(ink, init=False, feed_lines=0)
    assert payload.count(b"\x1dv0") == 3


def test_escpos_no_init_no_feed(ink: np.ndarray) -> None:
    payload = escpos_bytes(ink, init=False, feed_lines=0, cut=False)
    assert payload[:3] == b"\x1dv0"
    assert len(payload) == 8 + 48 * 120


def test_escpos_cut_appends_gs_v(ink: np.ndarray) -> None:
    payload = escpos_bytes(ink, init=False, feed_lines=0, cut=True)
    assert payload.endswith(b"\x1dV\x00")


def test_escpos_odd_width_pads_rows_to_bytes() -> None:
    """A 500-dot custom width wastes 4 bits per row, never 4 bytes."""
    ink = np.zeros((5, 500), dtype=bool)
    payload = escpos_bytes(ink, init=False, feed_lines=0)
    assert payload[4:6] == (63).to_bytes(2, "little")  # ceil(500 / 8)
    assert payload[6:8] == (5).to_bytes(2, "little")
    assert len(payload) == 8 + 63 * 5


def test_png_and_bmp_round_trip_odd_width() -> None:
    rng = np.random.default_rng(9)
    ink = rng.integers(0, 2, size=(7, 501)).astype(bool)
    for data, fmt in ((png_bytes(ink), "PNG"), (bmp_bytes(ink), "BMP")):
        image = Image.open(io.BytesIO(data))
        assert image.format == fmt
        assert image.mode == "1"
        assert image.size == (501, 7)
        assert np.array_equal(np.asarray(image) == 0, ink)


def parse_escpos(payload: bytes) -> tuple[int, np.ndarray]:
    """Independent ESC/POS reader - the contract a real print app has to meet.

    Written from the spec rather than from ``pack_1bit`` so that a packing bug
    cannot hide behind a matching "decoder".  Walks the stream the way firmware
    does: optional ``ESC @``, one or more ``GS v 0`` bands, then feed/cut.
    """
    pos = 0
    bands: list[np.ndarray] = []
    width_px = 0
    # Prefix -> command length, for the non-raster commands.
    commands = ((b"\x1b@", 2), (b"\x1bd", 3), (b"\x1dV\x00", 3))

    while pos < len(payload):
        for prefix, size in commands:
            if payload.startswith(prefix, pos):
                pos += size
                break
        else:
            assert payload.startswith(b"\x1dv0\x00", pos), (
                f"unexpected byte 0x{payload[pos]:02x} at {pos}"
            )
            x_bytes = int.from_bytes(payload[pos + 4 : pos + 6], "little")
            rows = int.from_bytes(payload[pos + 6 : pos + 8], "little")
            pos += 8
            width_px = x_bytes * 8
            body = payload[pos : pos + x_bytes * rows]
            assert len(body) == x_bytes * rows
            bits = np.unpackbits(np.frombuffer(body, dtype=np.uint8))
            bands.append(bits.reshape(rows, x_bytes * 8).astype(bool))
            pos += x_bytes * rows

    assert bands, "no raster bands in payload"
    return width_px, np.vstack(bands)


@pytest.mark.parametrize(
    "shape",
    [(1, 1), (1, 384), (5, 500), (120, 384), (2000, 384), (961, 576)],
)
def test_escpos_round_trips_through_an_independent_parser(shape: tuple[int, int]) -> None:
    rng = np.random.default_rng(11)
    ink = rng.integers(0, 2, size=shape).astype(bool)
    payload = escpos_bytes(ink, init=True, feed_lines=3, cut=True)

    width_px, decoded = parse_escpos(payload)

    assert width_px == (shape[1] + 7) // 8 * 8
    assert decoded.shape == (shape[0], width_px)
    # The printer prints whole bytes; anything past the real width must be blank.
    assert np.array_equal(decoded[:, : shape[1]], ink)
    assert not decoded[:, shape[1] :].any()


def test_escpos_padding_bits_are_blank() -> None:
    ink = np.ones((4, 500), dtype=bool)
    _, decoded = parse_escpos(escpos_bytes(ink, init=False, feed_lines=0))
    # The 4 bits past dot 500 are padding and must never be printed.
    assert decoded.shape == (4, 504)
    assert decoded[:, :500].all()
    assert not decoded[:, 500:].any()


def test_streams_are_identical_for_same_options(gradient_png) -> None:
    first = convert(gradient_png, ConvertOptions(dither=DitherMode.BAYER4))
    second = convert(gradient_png, ConvertOptions(dither=DitherMode.BAYER4))
    assert first.png_bytes() == second.png_bytes()


def test_half_block_text() -> None:
    ink = np.array(
        [
            [1, 1, 0, 0],
            [1, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1],
        ],
        dtype=bool,
    )
    text = half_block_text(ink, max_width=4)
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("\u2588")
    assert lines[1][0] == " "


def test_atomic_write_and_sidecar(tmp_path) -> None:
    target = tmp_path / "nested" / "out.png"
    atomic_write(target, b"hello")
    assert target.read_bytes() == b"hello"
    assert not list(tmp_path.glob("nested/.*.tmp"))

    write_sidecar(target, {"width": 384})
    assert (tmp_path / "nested" / "out.png.json").exists()


def test_atomic_write_replaces_existing(tmp_path) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    atomic_write(target, b"new")
    assert target.read_bytes() == b"new"


def test_atomic_write_locked_file_is_a_typed_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file held open must not surface as a bare PermissionError."""

    def locked(src, dst, *args, **kwargs):
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(os, "replace", locked)
    target = tmp_path / "held.png"
    target.write_bytes(b"old")

    with pytest.raises(OutputInUseError) as caught:
        atomic_write(target, b"new")

    assert "open in another application" in caught.value.message
    assert caught.value.hint
    # The original file is untouched and no temp file is left behind.
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_write_unwritable_folder_is_a_typed_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args, **kwargs):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(tempfile, "mkstemp", refuse)
    with pytest.raises(OutputError):
        atomic_write(tmp_path / "sub" / "out.png", b"x")


def test_empty_ink_rejected() -> None:
    with pytest.raises(ValueError):
        png_bytes(np.zeros((0, 0), dtype=bool))


def test_png_upscale_repeats_every_dot(ink: np.ndarray) -> None:
    image = Image.open(io.BytesIO(png_bytes(ink, upscale=3)))
    assert image.mode == "1"
    assert image.size == (384 * 3, 120 * 3)
    expected = np.repeat(np.repeat(ink, 3, axis=0), 3, axis=1)
    assert np.array_equal(np.asarray(image) == 0, expected)


def test_bmp_upscale_repeats_every_dot(ink: np.ndarray) -> None:
    image = Image.open(io.BytesIO(bmp_bytes(ink, upscale=2)))
    assert image.mode == "1"
    assert image.size == (384 * 2, 120 * 2)
    assert np.array_equal(
        np.asarray(image) == 0, np.repeat(np.repeat(ink, 2, axis=0), 2, axis=1)
    )


def test_upscale_one_is_byte_identical(ink: np.ndarray) -> None:
    assert png_bytes(ink, upscale=1) == png_bytes(ink)
    assert bmp_bytes(ink, upscale=1) == bmp_bytes(ink)


def test_upscale_rejects_zero(ink: np.ndarray) -> None:
    with pytest.raises(ValueError):
        png_bytes(ink, upscale=0)

