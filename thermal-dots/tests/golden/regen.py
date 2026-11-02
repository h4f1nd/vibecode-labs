"""Regenerate ``tests/golden/hashes.json``.

Run after an *intended* change to dithering or tone behaviour:

    .venv\\Scripts\\python tests\\golden\\regen.py

Then review the diff: every changed hash means pixels changed for every user.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from thermaldots.bits import pack_1bit
from thermaldots.models import ConvertOptions, DitherMode, Paper
from thermaldots.pipeline import convert

HASHES = Path(__file__).with_name("hashes.json")


def sample() -> Image.Image:
    width, height = 96, 72
    xs = np.linspace(0, 255, width, dtype=np.float32)[None, :]
    ys = np.linspace(0, 255, height, dtype=np.float32)[:, None]
    arr = np.stack(
        [
            np.broadcast_to(xs, (height, width)),
            np.broadcast_to(ys, (height, width)),
            np.broadcast_to((xs + ys) / 2, (height, width)),
        ],
        axis=-1,
    ).astype(np.uint8)
    image = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 8, 60, 56), fill=(250, 250, 250))
    draw.rectangle((64, 44, 90, 68), fill=(6, 6, 6))
    draw.line((0, 70, 95, 62), fill=(10, 10, 10), width=2)
    return image


def fingerprint(ink: np.ndarray) -> str:
    digest = hashlib.blake2b(pack_1bit(ink), digest_size=8)
    return f"{digest.hexdigest()}:{ink.shape[1]}x{ink.shape[0]}"


def cases() -> dict[str, ConvertOptions]:
    out: dict[str, ConvertOptions] = {}
    for paper in (Paper.MM58, Paper.MM80):
        for mode in DitherMode:
            out[f"{paper.value}/{mode.value}"] = ConvertOptions(paper=paper, dither=mode)
    out["58mm/tone"] = ConvertOptions(
        dither=DitherMode.BAYER4, gamma=1.25, contrast=1.15, brightness=6
    )
    out["58mm/invert"] = ConvertOptions(dither=DitherMode.NONE, invert=True)
    out["58mm/margin-border"] = ConvertOptions(
        dither=DitherMode.MEAN, margin=6, border=True, max_height_dots=120
    )
    return out


def build() -> dict[str, str]:
    image = sample()
    return {name: fingerprint(convert(image, options).ink) for name, options in cases().items()}


if __name__ == "__main__":
    payload = build()
    HASHES.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(payload)} fingerprints to {HASHES}")
