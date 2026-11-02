from __future__ import annotations

import csv
import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import dotdat.exporter as exporter
from dotdat.datfile import DatFile
from dotdat.errors import ExportError, OutputExistsError, QueryError
from dotdat.exporter import EXPORT_FORMATS, EXTENSIONS, export_table, select_fields
from dotdat.query import compile_filters

FORMATS = list(EXPORT_FORMATS)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_format_table() -> None:
    assert FORMATS == ["csv", "txt", "json", "jsonl", "html", "xml", "sql", "xlsx"]
    assert set(EXTENSIONS) == set(FORMATS)


@pytest.mark.parametrize("fmt", FORMATS)
def test_export_every_format(sample_dat: Path, tmp_path: Path, fmt: str) -> None:
    out = tmp_path / f"out.{EXTENSIONS[fmt]}"
    with DatFile(sample_dat) as table:
        count = export_table(table, out, fmt)
        row_count = table.count()
    assert count == row_count == 3
    assert out.exists() and out.stat().st_size > 0
    assert not list(tmp_path.glob(".*.tmp"))


def test_csv_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    with DatFile(sample_dat) as table:
        export_table(table, out, "csv")
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["ID", "NAME", "AMOUNT", "FLAG"]
    assert rows[1] == ["1", "ALPHA", "12.34", "A"]
    assert len(rows) == 4


def test_txt_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    with DatFile(sample_dat) as table:
        export_table(table, out, "txt")
    lines = read_text(out).splitlines()
    assert lines[0] == "ID\tNAME\tAMOUNT\tFLAG"
    assert len(lines) == 4


def test_json_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    with DatFile(sample_dat) as table:
        export_table(table, out, "json")
    payload = json.loads(read_text(out))
    assert payload[0] == {"ID": 1, "NAME": "ALPHA", "AMOUNT": "12.34", "FLAG": "A"}
    assert len(payload) == 3


def test_jsonl_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.jsonl"
    with DatFile(sample_dat) as table:
        export_table(table, out, "jsonl")
    lines = read_text(out).splitlines()
    assert len(lines) == 3
    assert json.loads(lines[1])["AMOUNT"] == "-5.00"


def test_html_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    with DatFile(sample_dat) as table:
        export_table(table, out, "html")
    body = read_text(out)
    assert "<table>" in body
    assert "<th>ID</th>" in body
    assert "<td>ALPHA</td>" in body


def test_xml_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xml"
    with DatFile(sample_dat) as table:
        export_table(table, out, "xml")
    root = ET.fromstring(read_text(out))
    assert root.tag == "table"
    assert len(root.findall("record")) == 3
    assert root.find("record/field").text == "1"


def test_sql_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.sql"
    with DatFile(sample_dat) as table:
        export_table(table, out, "sql")
    script = read_text(out)
    assert 'CREATE TABLE "RECORD"' in script
    assert "INSERT INTO" in script

    connection = sqlite3.connect(tmp_path / "check.db")
    try:
        connection.executescript(script)
        rows = connection.execute('SELECT "ID", "NAME" FROM "RECORD" ORDER BY "ID"').fetchall()
    finally:
        connection.close()
    assert rows == [(1, "ALPHA"), (2, "beta"), (3, "Gamma")]


def test_xlsx_contents(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    with DatFile(sample_dat) as table:
        export_table(table, out, "xlsx")
    from openpyxl import load_workbook

    workbook = load_workbook(out, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    assert rows[0] == ("ID", "NAME", "AMOUNT", "FLAG")
    assert rows[1][0] == 1
    assert rows[1][2] == 12.34
    assert len(rows) == 4


def test_include_deleted(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    with DatFile(sample_dat) as table:
        count = export_table(table, out, "csv", include_deleted=True)
    assert count == 4
    assert "DELETED" in read_text(out)


def test_filter_and_field_selection(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    with DatFile(sample_dat) as table:
        predicate = compile_filters(["ID>=2"], table.fields)
        count = export_table(
            table,
            out,
            "csv",
            predicate=predicate,
            fields=["ID", "NAME"],
        )
    assert count == 2
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows == [["ID", "NAME"], ["2", "beta"], ["3", "Gamma"]]


def test_sorting(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    with DatFile(sample_dat) as table:
        export_table(table, out, "csv", sort="AMOUNT", desc=True)
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert [row[2] for row in rows[1:]] == ["12.34", "0.00", "-5.00"]


def test_refuses_to_overwrite_source(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="source DAT"):
        export_table(table, sample_dat, "csv")


@pytest.mark.skipif(os.name != "nt", reason="needs a case-insensitive filesystem")
def test_refuses_source_with_different_case(sample_dat: Path) -> None:
    alias = sample_dat.with_name(sample_dat.name.lower())
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="source DAT"):
        export_table(table, alias, "csv", force=True)
    assert sample_dat.exists()


def test_write_failure_becomes_export_error(sample_dat: Path, tmp_path: Path) -> None:
    blocked = tmp_path / "folder"
    blocked.mkdir()
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="Cannot write"):
        export_table(table, blocked, "csv", force=True)
    assert not list(tmp_path.glob(".*.tmp"))


def test_excel_row_cap_is_checked_up_front(
    sample_dat: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exporter, "_EXCEL_MAX_ROWS", 3)
    out = tmp_path / "out.xlsx"
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="Excel"):
        export_table(table, out, "xlsx")
    assert not out.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_excel_row_cap_catches_filtered_overflow(
    sample_dat: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exporter, "_EXCEL_MAX_ROWS", 2)
    out = tmp_path / "out.xlsx"
    with DatFile(sample_dat) as table:
        predicate = compile_filters(["ID>=1"], table.fields)
        with pytest.raises(ExportError, match="Excel"):
            export_table(table, out, "xlsx", predicate=predicate)
    assert not out.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_cancel_stops_even_an_empty_export(tmp_path: Path) -> None:
    from datbuilder import SAMPLE_FIELDS, write_dat

    empty = write_dat(tmp_path / "EMPTY.DAT", SAMPLE_FIELDS, [])
    out = tmp_path / "out.csv"
    with DatFile(empty) as table, pytest.raises(ExportError, match="cancelled"):
        export_table(table, out, "csv", cancel=lambda: True)
    assert not out.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_existing_output_needs_force(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    out.write_text("keep me", encoding="utf-8")
    with DatFile(sample_dat) as table:
        with pytest.raises(OutputExistsError):
            export_table(table, out, "csv")
        assert read_text(out) == "keep me"
        export_table(table, out, "csv", force=True)
    assert read_text(out).startswith("ID,")


def test_unknown_format(sample_dat: Path, tmp_path: Path) -> None:
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="Unknown export format"):
        export_table(table, tmp_path / "out.bin", "nope")


def test_cancel_leaves_no_file(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="cancelled"):
        export_table(table, out, "csv", cancel=lambda: True)
    assert not out.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_cancel_after_some_rows(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    seen = {"count": 0}

    def cancel() -> bool:
        seen["count"] += 1
        return seen["count"] > 2

    with DatFile(sample_dat) as table, pytest.raises(ExportError, match="cancelled"):
        export_table(table, out, "csv", cancel=cancel)
    assert not out.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_unknown_field(sample_dat: Path, tmp_path: Path) -> None:
    with DatFile(sample_dat) as table, pytest.raises(QueryError, match="Unknown field"):
        export_table(table, tmp_path / "out.csv", "csv", fields=["NOPE"])


def test_select_fields_rejects_duplicates_and_keeps_order(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        selected = select_fields(table, ["NAME", "ID", "NAME"])
    assert [field.name for field in selected] == ["NAME", "ID"]


def test_select_fields_empty(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        assert select_fields(table, None) == list(table.fields)


def test_export_creates_parent(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "deep" / "nested" / "out.csv"
    with DatFile(sample_dat) as table:
        export_table(table, out, "csv")
    assert out.exists()


def test_progress_reports_last_row(sample_dat: Path, tmp_path: Path) -> None:
    seen: list[tuple[int, int | None]] = []
    with DatFile(sample_dat) as table:
        export_table(
            table,
            tmp_path / "out.csv",
            "csv",
            progress=lambda done, total: seen.append((done, total)),
        )
    assert seen[0] == (1, 3)
    assert seen[-1] == (3, 3)
