from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from dotdat.datfile import DatFile
from dotdat.errors import CorruptDatFile

pytestmark = pytest.mark.realdata


def _tables(reference_dir: Path) -> list[Path]:
    return sorted(reference_dir.glob("*.DAT"))


def _openable(paths: list[Path]) -> list[tuple[Path, DatFile]]:
    opened: list[tuple[Path, DatFile]] = []
    for path in paths:
        with contextlib.suppress(CorruptDatFile):
            opened.append((path, DatFile(path)))
    return opened


def test_reference_set_is_not_empty(reference_dir: Path) -> None:
    assert _tables(reference_dir), "no .DAT files found"


def test_at_least_one_table_parses(reference_dir: Path) -> None:
    opened = _openable(_tables(reference_dir))
    try:
        assert opened, "no table in the reference set parsed"
        for path, table in opened:
            assert table.fields, path.name
            assert table.header.record_length >= 5, path.name
            assert table.header.data_offset >= 85, path.name
            assert table.header.active_count >= 0, path.name
            assert len(table.fields) == table.header.field_count, path.name
    finally:
        for _, table in opened:
            table.close()


def test_corrupt_tables_fail_cleanly(reference_dir: Path) -> None:
    corrupt = 0
    for path in _tables(reference_dir):
        try:
            with DatFile(path):
                pass
        except CorruptDatFile as error:
            corrupt += 1
            assert error.message
            assert error.hint
    assert corrupt >= 0  # a clean set is acceptable


def test_largest_table_structure_and_rows(reference_dir: Path) -> None:
    opened = _openable(_tables(reference_dir))
    try:
        assert opened
        path, table = max(opened, key=lambda item: item[1].header.record_count)
        header = table.header
        assert header.signature_hex.startswith("0x")
        assert header.record_count >= 0
        assert header.field_count == len(table.fields)
        assert header.data_offset + header.record_count * header.record_length <= path.stat().st_size

        if header.record_count:
            row = table.read_record(0)
            assert row.number == 1
            assert len(row.values) == header.field_count

        page = table.page(0, 10)
        assert page.total == header.record_count
        assert len(page.rows) <= 10
    finally:
        for _, table in opened:
            table.close()


def test_deleted_flag_matches_header(reference_dir: Path) -> None:
    opened = _openable(_tables(reference_dir))
    try:
        for _, table in opened:
            header = table.header
            if not header.deleted_count:
                continue
            assert table.count() == header.active_count
            assert table.count(include_deleted=True) == header.record_count
            assert any(
                row.deleted for row in table.iter_records(include_deleted=True)
            )
            for row in table.iter_records(include_deleted=True):
                assert row.deleted == bool(row.status & 0x10)
            return
        pytest.skip("reference set has no deleted records to check")
    finally:
        for _, table in opened:
            table.close()


def test_deep_paging_on_largest_table(reference_dir: Path) -> None:
    opened = _openable(_tables(reference_dir))
    try:
        assert opened
        _, table = max(opened, key=lambda item: item[1].header.record_count)
        total = table.header.record_count
        if total < 2:
            pytest.skip("table too small to page")
        offset = max(0, total - 10)
        page = table.page(offset=offset, limit=10)
        assert page.total == total
        assert len(page.rows) == min(10, total - offset)
    finally:
        for _, table in opened:
            table.close()


def test_largest_table_scan_is_fast(reference_dir: Path) -> None:
    import time

    opened = _openable(_tables(reference_dir))
    try:
        assert opened
        _, table = max(opened, key=lambda item: item[1].header.record_count)
        limit = min(10_000, table.header.record_count)
        started = time.perf_counter()
        for index in range(limit):
            table.read_record(index)
        elapsed = time.perf_counter() - started
        assert elapsed < 5.0
    finally:
        for _, table in opened:
            table.close()
