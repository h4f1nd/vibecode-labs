"""Shared fixtures: synthetic images with known structure (no binary blobs)."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw


def make_gradient(width: int = 640, height: int = 480) -> Image.Image:
    """Photo-ish RGB image: two gradients plus hard-edged shapes."""
    x = np.linspace(0, 255, width, dtype=np.float32)[None, :].repeat(height, axis=0)
    y = np.linspace(0, 255, height, dtype=np.float32)[:, None].repeat(width, axis=1)
    arr = np.stack([x, y, (x + y) / 2.0], axis=-1).astype(np.uint8)
    image = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (width * 0.3, height * 0.3, width * 0.7, height * 0.7), fill=(250, 250, 250)
    )
    draw.rectangle((8, 8, 90, 90), fill=(8, 8, 8))
    return image


@pytest.fixture(scope="session")
def gradient_jpeg(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("images")
    path = folder / "gradient.jpg"
    make_gradient().save(path, quality=92)
    return path


@pytest.fixture(scope="session")
def gradient_png(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("images")
    path = folder / "gradient.png"
    make_gradient().save(path)
    return path


@pytest.fixture(scope="session")
def alpha_png(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("images")
    path = folder / "alpha.png"
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 111, 111), fill=(0, 0, 0, 255))
    image.save(path)
    return path


@pytest.fixture(scope="session")
def tiny_png(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("images")
    path = folder / "tiny.png"
    Image.new("RGB", (1, 1), (0, 0, 0)).save(path)
    return path


@pytest.fixture(scope="session")
def corrupt_file(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("images")
    path = folder / "broken.jpg"
    path.write_bytes(b"this is definitely not a jpeg")
    return path
