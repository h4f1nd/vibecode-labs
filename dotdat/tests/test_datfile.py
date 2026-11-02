from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from datbuilder import SAMPLE_FIELDS, SAMPLE_ROWS, write_dat, write_sample
from dotdat.datfile import DatFile
from dotdat.errors import (
    CorruptDatFile,
    DotDatError,
    NotADatFile,
    QueryError,
    TruncatedDatFile,
)


def test_header(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        header = table.header
        assert header.signature_hex == "0x3343"
        assert header.record_count == 4
        assert header.deleted_count == 1
        assert header.active_count == 3
        assert header.field_count == 4
        assert header.key_count == 1
        assert header.record_length == 5 + 21
        assert header.payload_size == 21
        assert header.record_name == "RECORD"
        assert header.file_prefix == "TST"
        assert header.data_offset == 85 + 4 * 27 + 19 + 6


def test_fields_are_normalized_but_keep_raw_name(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        assert [field.name for field in table.fields] == ["ID", "NAME", "AMOUNT", "FLAG"]
        assert table.fields[0].raw_name == "TST:ID"
        assert table.fields[2].decimals == 2
        assert table.resolve_field("id").index == 1
        assert table.resolve_field("TST:ID").index == 1
        with pytest.raises(QueryError, match="Unknown field"):
            table.resolve_field("NOPE")


def test_keys(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        assert len(table.keys) == 1
        key = table.keys[0]
        assert key.name == "ID_KEY"
        assert key.components == 1
        assert key.parts[0].field_number == 1
        assert key.parts[0].offset == 0
        assert key.parts[0].length == 4


def test_records(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        row = table.read_record(0)
        assert row.number == 1
        assert row.deleted is False
        assert row.values == {
            "ID": 1,
            "NAME": "ALPHA",
            "AMOUNT": Decimal("12.34"),
            "FLAG": "A",
        }
        assert row.to_dict()["values"]["AMOUNT"] == "12.34"
        assert table.read_record(1).values["AMOUNT"] == Decimal("-5.00")
        assert table.read_record(3).deleted is True


def test_page_hides_deleted_by_default(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        page = table.page(offset=0, limit=10)
        assert page.total == 3
        assert [row.number for row in page.rows] == [1, 2, 3]
        assert page.has_more is False


def test_page_can_include_deleted(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        page = table.page(offset=0, limit=10, include_deleted=True)
        assert page.total == 4
        assert [row.number for row in page.rows] == [1, 2, 3, 4]
        assert page.rows[-1].deleted is True


def test_paging_and_offsets(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        page = table.page(offset=1, limit=1)
        assert [row.number for row in page.rows] == [2]
        assert page.has_more is True
        page = table.page(offset=2, limit=1)
        assert [row.number for row in page.rows] == [3]
        assert page.has_more is False


def test_filters(sample_dat: Path) -> None:
    from dotdat.query import compile_filters

    with DatFile(sample_dat) as table:
        predicate = compile_filters(["AMOUNT>=0", "NAME~a"], table.fields)
        assert predicate is not None
        page = table.page(0, 10, predicate=predicate)
        assert [row.values["ID"] for row in page.rows] == [1, 3]
        assert page.total is None
        assert table.count(predicate=predicate) == 2
        # The fast path decodes only AMOUNT and NAME to test the row, then
        # re-reads the full record before yielding it.
        assert page.rows[0].values["FLAG"] == "A"


def test_predicate_without_field_hints_still_works(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        predicate = lambda row: row.values["ID"] % 2 == 1  # noqa: E731
        page = table.page(0, 10, predicate=predicate)
        assert [row.values["ID"] for row in page.rows] == [1, 3]
        assert table.count(predicate=predicate) == 2


def test_filters_accept_prefixed_names(sample_dat: Path) -> None:
    from dotdat.query import compile_filters

    with DatFile(sample_dat) as table:
        predicate = compile_filters(["TST:NAME=alpha"], table.fields)
        assert predicate is not None
        assert predicate.fields == ("NAME",)
        page = table.page(0, 10, predicate=predicate)
        assert [row.values["ID"] for row in page.rows] == [1]


def test_sorting(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        asc = table.page(0, 10, sort="AMOUNT")
        assert [row.values["AMOUNT"] for row in asc.rows] == [
            Decimal("-5.00"),
            Decimal("0.00"),
            Decimal("12.34"),
        ]
        desc = table.page(0, 10, sort="AMOUNT", desc=True)
        assert [row.values["AMOUNT"] for row in desc.rows] == [
            Decimal("12.34"),
            Decimal("0.00"),
            Decimal("-5.00"),
        ]
        assert asc.total == 3


def test_iter_records_start(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        rows = list(table.iter_records(start=2))
        assert [row.values["ID"] for row in rows] == [3]


def test_info(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        info = table.info_dict()
        assert info["file_name"] == "SAMPLE.DAT"
        assert info["header"]["record_count"] == 4
        assert info["fields"][0]["name"] == "ID"
        assert info["fields"][0]["raw_name"] == "TST:ID"
        assert info["keys"][0]["name"] == "ID_KEY"
        assert info["last_change"] == "2026-01-31 01:00:00"
        assert "date_fields" in info


def test_date_fields_flag_clarion_day_counts(tmp_path: Path) -> None:
    from datbuilder import FieldSpec

    fields = [
        FieldSpec(name="DATE", type_code=1, length=4),
        FieldSpec(name="TIME", type_code=1, length=4),
    ]
    rows = [{"DATE": 73_928 + index, "TIME": 4_000_000 + index} for index in range(10)]
    path = write_dat(tmp_path / "DATES.DAT", fields, rows)

    with DatFile(path) as table:
        assert table.date_fields() == ("DATE",)
        assert table.info_dict()["date_fields"] == ["DATE"]


def test_date_fields_ignore_empty_dates(tmp_path: Path) -> None:
    from datbuilder import FieldSpec

    fields = [FieldSpec(name="DATE", type_code=1, length=4)]
    path = write_dat(tmp_path / "EMPTY_DATES.DAT", fields, [{"DATE": 0}] * 5)

    with DatFile(path) as table:
        assert table.date_fields() == ()


def test_date_fields_ignore_mixed_columns(tmp_path: Path) -> None:
    from datbuilder import FieldSpec

    fields = [FieldSpec(name="COUNTER", type_code=1, length=4)]
    rows = [{"COUNTER": 73_928}] * 8 + [{"COUNTER": 4_000_000}] * 2
    path = write_dat(tmp_path / "MIXED.DAT", fields, rows)

    with DatFile(path) as table:
        assert table.date_fields() == ()


def test_bad_page_size(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        with pytest.raises(QueryError, match="Page size"):
            table.page(limit=0)
        with pytest.raises(QueryError, match="Page size"):
            table.page(limit=10_001)


def test_read_record_out_of_range(sample_dat: Path) -> None:
    with DatFile(sample_dat) as table:
        with pytest.raises(IndexError):
            table.read_record(4)
        with pytest.raises(IndexError):
            table.read_record(-1)


def test_not_a_dat_file(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", signature=0x1234)
    with pytest.raises(NotADatFile, match=r"not a Clarion 2\.x DAT"):
        DatFile(path)


def test_unknown_encoding(sample_dat: Path) -> None:
    with pytest.raises(DotDatError, match="Unknown text encoding"):
        DatFile(sample_dat, encoding="not-a-codec")


def test_implausible_field_count(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", field_count=60_000)
    with pytest.raises(CorruptDatFile, match="60000 fields"):
        DatFile(path)


def test_zero_fields_rejected(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", field_count=0)
    with pytest.raises(CorruptDatFile):
        DatFile(path)


def test_short_record_length(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", record_length=4)
    with pytest.raises(CorruptDatFile, match="minimum is 5"):
        DatFile(path)


def test_field_does_not_fit(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", record_length=15)
    with pytest.raises(CorruptDatFile, match="does not fit"):
        DatFile(path)


def test_data_offset_before_schema(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", data_offset=10)
    with pytest.raises(CorruptDatFile, match="before the schema"):
        DatFile(path)


def test_data_offset_beyond_file(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", data_offset=10_000)
    with pytest.raises(TruncatedDatFile, match="beyond"):
        DatFile(path)


def test_record_count_beyond_file(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", record_count=1000)
    with pytest.raises(TruncatedDatFile, match="declares 1,000 records"):
        DatFile(path)


def test_short_file(tmp_path: Path) -> None:
    path = tmp_path / "EMPTY.DAT"
    path.write_bytes(b"")
    with pytest.raises(TruncatedDatFile, match="header needs 85"):
        DatFile(path)


def test_truncated_header(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", truncate=40)
    with pytest.raises(TruncatedDatFile):
        DatFile(path)


def test_field_descriptor_truncated(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", truncate=100)
    with pytest.raises(TruncatedDatFile, match="field descriptor"):
        DatFile(path)


def test_key_truncated(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", truncate=85 + 4 * 27 + 10)
    with pytest.raises(TruncatedDatFile, match="key definition"):
        DatFile(path)


def test_key_parts_truncated(tmp_path: Path) -> None:
    path = write_sample(tmp_path / "BAD.DAT", truncate=85 + 4 * 27 + 20)
    with pytest.raises(TruncatedDatFile, match="parts of key"):
        DatFile(path)


def test_close_is_idempotent(sample_dat: Path) -> None:
    table = DatFile(sample_dat)
    table.close()
    table.close()


def test_no_keys(tmp_path: Path) -> None:
    path = write_dat(tmp_path / "NOKEY.DAT", SAMPLE_FIELDS, SAMPLE_ROWS)
    with DatFile(path) as table:
        assert table.keys == ()
        assert table.header.key_count == 0


def test_empty_table(tmp_path: Path) -> None:
    path = write_dat(tmp_path / "EMPTY.DAT", SAMPLE_FIELDS, [])
    with DatFile(path) as table:
        page = table.page()
        assert page.rows == ()
        assert page.total == 0
        assert table.count() == 0


def test_custom_prefix_absent(tmp_path: Path) -> None:
    from datbuilder import FieldSpec

    fields = [FieldSpec(name="PLAIN", type_code=1, length=4)]
    path = write_dat(
        tmp_path / "PLAIN.DAT",
        fields,
        [{"PLAIN": 7}],
        file_prefix="",
    )
    with DatFile(path) as table:
        assert table.fields[0].name == "PLAIN"
        assert table.fields[0].raw_name == "PLAIN"
        assert table.read_record(0).values["PLAIN"] == 7
