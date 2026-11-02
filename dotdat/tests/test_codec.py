from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from dotdat.codec import (
    CLARION_EPOCH,
    clarion_date,
    clarion_time,
    decode_decimal,
    decode_string,
    decode_value,
    display_value,
    format_clarion_timestamp,
)
from dotdat.models import FieldDef


def field(type_code: int, length: int, decimals: int = 0, array: int = 0) -> FieldDef:
    return FieldDef(
        index=1,
        name="VALUE",
        type_code=type_code,
        offset=0,
        length=length,
        significant=0,
        decimals=decimals,
        array_number=array,
        picture_number=0,
    )


class TestDecimal:
    def test_positive(self) -> None:
        assert decode_decimal(bytes.fromhex("000000200000"), 2) == Decimal("2000.00")

    def test_negative(self) -> None:
        assert decode_decimal(bytes.fromhex("800000050000"), 2) == Decimal("-500.00")

    def test_zero(self) -> None:
        assert decode_decimal(bytes(6), 2) == Decimal("0.00")

    def test_no_fraction(self) -> None:
        assert decode_decimal(bytes.fromhex("000000123456"), 0) == Decimal("123456")

    def test_sign_nibble_nine_is_negative(self) -> None:
        assert decode_decimal(bytes.fromhex("900000000001"), 0) == Decimal("-1")

    def test_empty(self) -> None:
        assert decode_decimal(b"", 2) == Decimal("0")

    def test_invalid_nibble(self) -> None:
        with pytest.raises(ValueError, match="invalid packed decimal"):
            decode_decimal(bytes.fromhex("00FF"), 0)


class TestValues:
    def test_long(self) -> None:
        assert decode_value(field(1, 4), (1234).to_bytes(4, "little", signed=True)) == 1234

    def test_negative_long(self) -> None:
        assert decode_value(field(1, 4), (-2).to_bytes(4, "little", signed=True)) == -2

    def test_string_strips_padding(self) -> None:
        assert decode_string(b"ALPHA\x00\x00\x00\x00\x00", "cp437") == "ALPHA"
        assert decode_string(b"ALPHA     ", "cp437") == "ALPHA"

    def test_string_cp437(self) -> None:
        assert decode_string(bytes([0x82]), "cp437") == "é"

    def test_string_chooses_encoding(self) -> None:
        assert decode_string(bytes([0xE9]), "latin-1") == "é"

    def test_decimal(self) -> None:
        assert decode_value(field(8, 6, 2), bytes.fromhex("000000200000")) == Decimal("2000.00")

    def test_byte_and_short(self) -> None:
        assert decode_value(field(5, 1), b"\x2a") == 42
        assert decode_value(field(6, 2), (300).to_bytes(2, "little", signed=True)) == 300

    def test_real(self) -> None:
        import struct

        assert decode_value(field(2, 8), struct.pack("<d", 1.5)) == 1.5

    def test_array_keeps_bytes(self) -> None:
        assert decode_value(field(3, 4, array=2), b"ABCD") == b"ABCD"

    def test_unknown_type_keeps_bytes(self) -> None:
        assert decode_value(field(99, 2), b"\x01\x02") == b"\x01\x02"

    def test_zero_length_is_empty(self) -> None:
        for type_code in (1, 3, 5, 6, 8, 99):
            assert decode_value(field(type_code, 0), b"") == ""

    def test_display(self) -> None:
        assert display_value(None) == ""
        assert display_value(Decimal("12.30")) == "12.30"
        assert display_value(b"\x01\x02") == "01 02"
        assert display_value(7) == "7"


class TestCalendar:
    def test_epoch(self) -> None:
        assert date(1800, 12, 28) == CLARION_EPOCH
        assert clarion_date(1) == date(1800, 12, 29)

    def test_known_date(self) -> None:
        assert clarion_date(82_214) == date(2026, 1, 31)

    def test_zero_date_is_none(self) -> None:
        assert clarion_date(0) is None
        assert clarion_date(-3) is None

    def test_time(self) -> None:
        assert clarion_time(0) == time(0, 0)
        assert clarion_time(360_000) == time(1, 0, 0)

    def test_bad_time(self) -> None:
        assert clarion_time(-1) is None
        assert clarion_time(8_640_000) is None

    def test_timestamp(self) -> None:
        assert format_clarion_timestamp(82_214, 360_000) == "2026-01-31 01:00:00"
        assert format_clarion_timestamp(0, 0) == "not recorded"
