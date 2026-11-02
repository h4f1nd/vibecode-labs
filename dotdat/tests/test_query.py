from __future__ import annotations

from decimal import Decimal

import pytest

from dotdat.errors import QueryError
from dotdat.models import FieldDef, RecordRow
from dotdat.query import compile_filters, parse_filter


def field(name: str, type_code: int, decimals: int = 0) -> FieldDef:
    return FieldDef(
        index=1,
        name=name,
        type_code=type_code,
        offset=0,
        length=4,
        significant=0,
        decimals=decimals,
        array_number=0,
        picture_number=0,
    )


FIELDS = [
    field("ID", 1),
    field("NAME", 3),
    field("AMOUNT", 8, 2),
    field("FLAG", 3),
]


def row(**values: object) -> RecordRow:
    return RecordRow(index=0, status=1, deleted=False, values=values)


class TestParse:
    def test_equals(self) -> None:
        expr = parse_filter("ID=42")
        assert (expr.field, expr.op, expr.value) == ("ID", "=", "42")

    def test_spaces(self) -> None:
        expr = parse_filter(" NAME >= 42 ")
        assert (expr.field, expr.op, expr.value) == ("NAME", ">=", "42")

    def test_contains_words(self) -> None:
        assert parse_filter("NAME contains sample").op == "~="

    def test_tilde(self) -> None:
        assert parse_filter("NAME~sample").op == "~"

    def test_quotes(self) -> None:
        assert parse_filter('NAME="SAMPLE CUSTOMER"').value == "SAMPLE CUSTOMER"
        assert parse_filter("NAME='X'").value == "X"

    def test_not_equal_variants(self) -> None:
        assert parse_filter("FLAG!=A").op == "!="
        assert parse_filter("FLAG<>A").op == "<>"

    def test_invalid(self) -> None:
        with pytest.raises(QueryError, match="Cannot parse"):
            parse_filter("NONSENSE")
        with pytest.raises(QueryError, match="no value"):
            parse_filter("NAME~")

    def test_empty_equals_allowed(self) -> None:
        assert parse_filter("NAME=").value == ""


class TestCompile:
    def test_empty_is_none(self) -> None:
        assert compile_filters([], FIELDS) is None

    def test_reports_used_fields_once(self) -> None:
        predicate = compile_filters(["ID>=2", "NAME~a", "ID<10"], FIELDS)
        assert predicate is not None
        assert predicate.fields == ("ID", "NAME")

    def test_numeric(self) -> None:
        predicate = compile_filters(["ID>=2", "AMOUNT<10"], FIELDS)
        assert predicate is not None
        assert predicate(row(ID=2, AMOUNT=Decimal("5.00"))) is True
        assert predicate(row(ID=1, AMOUNT=Decimal("5.00"))) is False
        assert predicate(row(ID=3, AMOUNT=Decimal("50.00"))) is False

    def test_equality_is_case_insensitive(self) -> None:
        predicate = compile_filters(["NAME=alpha"], FIELDS)
        assert predicate is not None
        assert predicate(row(NAME="ALPHA")) is True
        assert predicate(row(NAME="alpha")) is True
        assert predicate(row(NAME="beta")) is False

    def test_not_equal(self) -> None:
        predicate = compile_filters(["NAME!=alpha"], FIELDS)
        assert predicate is not None
        assert predicate(row(NAME="beta")) is True
        assert predicate(row(NAME="ALPHA")) is False

    def test_contains_tilde_and_word(self) -> None:
        for expression in ("NAME~ahm", "NAME~=ahm", "NAME contains ahm"):
            predicate = compile_filters([expression], FIELDS)
            assert predicate is not None
            assert predicate(row(NAME="Ahmad Subarjo")) is True
            assert predicate(row(NAME="Budi")) is False

    def test_contains_works_on_numbers(self) -> None:
        predicate = compile_filters(["ID~12"], FIELDS)
        assert predicate is not None
        assert predicate(row(ID=123)) is True
        assert predicate(row(ID=456)) is False

    def test_text_order(self) -> None:
        predicate = compile_filters(["NAME>B"], FIELDS)
        assert predicate is not None
        assert predicate(row(NAME="Charlie")) is True
        assert predicate(row(NAME="Alpha")) is False

    def test_unknown_field(self) -> None:
        with pytest.raises(QueryError, match="Unknown field"):
            compile_filters(["NOPE=1"], FIELDS)

    def test_bad_number(self) -> None:
        with pytest.raises(QueryError, match="not a valid LONG"):
            compile_filters(["ID=abc"], FIELDS)
        with pytest.raises(QueryError, match="not a valid DECIMAL"):
            compile_filters(["AMOUNT=abc"], FIELDS)

    def test_and_semantics(self) -> None:
        predicate = compile_filters(["ID>=2", "FLAG=A"], FIELDS)
        assert predicate is not None
        assert predicate(row(ID=2, FLAG="A")) is True
        assert predicate(row(ID=2, FLAG="B")) is False
        assert predicate(row(ID=1, FLAG="A")) is False
