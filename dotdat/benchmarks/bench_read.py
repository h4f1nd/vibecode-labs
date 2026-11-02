r"""Read-only benchmarks for the DOTDAT engine.

    .venv\Scripts\python benchmarks\bench_read.py
    .venv\Scripts\python benchmarks\bench_read.py "C:\data\SAMPLE.DAT"
    .venv\Scripts\python benchmarks\bench_read.py --repeat 1

With no path, the script uses the largest ``.DAT`` in ``$DOTDAT_REFERENCE``
(default: a local ``reference`` folder). It never writes to the source table:
it opens, pages, scans and counts; nothing is exported.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotdat.datfile import DatFile
from dotdat.query import compile_filters


def timed(label: str, repeats: int, action: Callable[[], Any]) -> Any:
    samples: list[float] = []
    result: Any = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = action()
        samples.append(time.perf_counter() - started)
    best = min(samples)
    median = statistics.median(samples)
    print(f"{label:<34} best {best * 1000:8.1f} ms   median {median * 1000:8.1f} ms")
    return result


def default_table() -> Path:
    root = Path(os.environ.get("DOTDAT_REFERENCE", "reference"))
    candidates = sorted(
        root.glob("*.DAT"), key=lambda item: item.stat().st_size, reverse=True
    )
    return candidates[0] if candidates else root / "SAMPLE.DAT"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=default_table())
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    path: Path = args.path
    if not path.is_file():
        print(f"not found: {path}")
        return 1

    repeats: int = max(1, args.repeat)
    print(f"file      {path}")
    print(f"size      {path.stat().st_size:,} bytes")
    print(f"repeat    {repeats}")
    print()

    def open_close() -> int:
        with DatFile(path) as table:
            return table.header.record_count

    total = timed("open + parse + close", repeats, open_close)
    print(f"records   {total:,}")
    print()

    table = DatFile(path)
    try:
        timed("first page (100 rows)", repeats, lambda: table.page(0, 100))
        timed("deep page (100 rows)", repeats, lambda: table.page(100_000, 100))
        timed(
            "read 100,000 records",
            repeats,
            lambda: sum(1 for index in range(100_000) if table.read_record(index)),
        )

        text_field = next((f.name for f in table.fields if f.type_name == "STRING"), None)
        number_field = next(
            (f.name for f in table.fields if f.type_name in {"LONG", "DECIMAL", "REAL"}),
            None,
        )

        if text_field:
            text_predicate = compile_filters([f"{text_field}~1"], table.fields)
            if text_predicate is not None:
                matches = timed(
                    f"filter scan {text_field}~1 (all rows)",
                    repeats,
                    lambda: table.count(predicate=text_predicate),
                )
                print(f"matches   {matches:,}")
                timed(
                    "first page with filter",
                    repeats,
                    lambda: table.page(0, 100, predicate=text_predicate),
                )

        if number_field:
            number_predicate = compile_filters([f"{number_field}>=0"], table.fields)
            if number_predicate is not None:
                matches = timed(
                    f"filter scan {number_field}>=0 (all rows)",
                    repeats,
                    lambda: table.count(predicate=number_predicate),
                )
                print(f"matches   {matches:,}")
    finally:
        table.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
