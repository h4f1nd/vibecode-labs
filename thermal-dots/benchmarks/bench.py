"""Synthetic benchmark: 12 MP JPEG -> 58/80 mm dots.

Run with the project venv:

    .venv\\Scripts\\python benchmarks\\bench.py
    .venv\\Scripts\\python benchmarks\\bench.py --repeat 5 --width 4000 --height 3000
"""

from __future__ import annotations

import argparse
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from thermaldots.models import ConvertOptions, DitherMode, Paper
from thermaldots.pipeline import clear_cache, convert


def make_photo(width: int, height: int) -> Image.Image:
    """Deterministic photo-ish test image (gradients, shapes, fine noise)."""
    xs = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    red = (xs * 0.8 + 0.1) * 255
    green = (ys * 0.7 + 0.2) * 255
    blue = ((1 - xs) * 0.5 + ys * 0.4) * 255
    rgb = np.stack(
        [
            np.broadcast_to(red, (height, width)),
            np.broadcast_to(green, (height, width)),
            np.broadcast_to(blue, (height, width)),
        ],
        axis=-1,
    )
    rng = np.random.default_rng(42)
    rgb += rng.normal(0, 6, size=rgb.shape)
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")

    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (width * 0.18, height * 0.2, width * 0.55, height * 0.72), fill=(245, 243, 235)
    )
    draw.rectangle((width * 0.62, height * 0.42, width * 0.9, height * 0.86), fill=(12, 12, 14))
    draw.line((0, height * 0.9, width, height * 0.62), fill=(20, 20, 20), width=6)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--keep", action="store_true", help="keep the generated JPEG")
    args = parser.parse_args()

    folder = Path(tempfile.mkdtemp(prefix="thermaldots-bench-"))
    source = folder / "bench.jpg"

    started = time.perf_counter()
    make_photo(args.width, args.height).save(source, quality=92)
    print(
        f"source: {args.width}x{args.height} JPEG, "
        f"{source.stat().st_size / 1e6:.1f} MB, generated in "
        f"{(time.perf_counter() - started) * 1000:.0f} ms"
    )
    print()

    header = f"{'paper':<8}{'dither':<12}{'dots':>12}{'total ms':>10}{'dither ms':>11}{'ink %':>8}"
    print(header)
    print("-" * len(header))

    for paper in (Paper.MM58, Paper.MM80):
        for mode in DitherMode:
            timings: list[float] = []
            dither_ms: list[float] = []
            result = None
            for _ in range(args.repeat):
                clear_cache()  # measure the cold path (decode included)
                started = time.perf_counter()
                result = convert(source, ConvertOptions(paper=paper, dither=mode))
                timings.append((time.perf_counter() - started) * 1000)
                dither_ms.append(result.timings["dither"])
            assert result is not None
            print(
                f"{paper.value:<8}{mode.value:<12}"
                f"{result.width}x{result.height:<7}"
                f"{statistics.median(timings):>10.1f}"
                f"{statistics.median(dither_ms):>11.1f}"
                f"{result.ink_ratio * 100:>8.1f}"
            )
        print()

    print("Reminder: conversion is the fast part - sending 28-56 kB over")
    print("Bluetooth is what takes seconds, and that is your print app's job.")

    if not args.keep:
        for path in folder.glob("*"):
            path.unlink(missing_ok=True)
        folder.rmdir()
    else:
        print(f"kept: {source}")


if __name__ == "__main__":
    main()
