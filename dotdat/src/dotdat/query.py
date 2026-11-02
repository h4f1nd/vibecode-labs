"""Tiny filter language for the CLI and GUI.

Supported expressions, combined with AND::

    YEAR=2026
    NAME~sample              (contains, case-insensitive)
    BALANCE>=1000
    AREA!=01
    ACCOUNT<=1000000000
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .codec import display_value
from .errors import QueryError
from .models import FieldDef, RecordRow

_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9_:.\-]+)\s*(>=|<=|!=|<>|~=|contains|~|=|>|<)\s*(.*)$",
    re.IGNORECASE,
)
_QUOTES = ("'", '"')


@dataclass(frozen=True, slots=True)
class FilterExpr:
    field: str
    op: str
    value: str


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES:
        return value[1:-1]
    return value


def parse_filter(text: str) -> FilterExpr:
    """Parse one expression such as ``NAME~sample``."""
    match = _PATTERN.match(text)
    if match is None:
        raise QueryError(
            f"Cannot parse filter {text!r}.",
            hint="Use FIELD=VALUE, FIELD~TEXT, or FIELD>=NUMBER. "
            "Example: YEAR=2026 or NAME~sample",
        )
    field, op, raw_value = match.groups()
    op = op.casefold()
    if op == "contains":
        op = "~="
    value = _unquote(raw_value.strip())
    if not value and op not in ("=", "!=", "<>"):
        raise QueryError(
            f"Filter {text!r} has no value.",
            hint="Add a value after the operator, for example YEAR=2026.",
        )
    return FilterExpr(field=field, op=op, value=value)


@dataclass(frozen=True, slots=True)
class Filter:
    """A compiled filter that also knows which fields it touches."""

    checks: tuple[Callable[[RecordRow], bool], ...]
    fields: tuple[str, ...]

    def __call__(self, row: RecordRow) -> bool:
        return all(check(row) for check in self.checks)


def compile_filters(
    expressions: Sequence[str],
    fields: Sequence[FieldDef],
) -> Filter | None:
    """Compile expressions into one predicate, or ``None`` when empty."""
    if not expressions:
        return None

    by_name: dict[str, FieldDef] = {}
    for field in fields:
        by_name.setdefault(field.name.casefold(), field)
        if field.raw_name:
            by_name.setdefault(field.raw_name.casefold(), field)
    checks: list[Callable[[RecordRow], bool]] = []
    used: list[str] = []
    for expression in expressions:
        parsed = parse_filter(expression)
        target = by_name.get(parsed.field.casefold())
        if target is None:
            available = ", ".join(item.name for item in fields[:12])
            raise QueryError(
                f"Unknown field {parsed.field!r} in filter {expression!r}.",
                hint=f"Available fields: {available}",
            )
        checks.append(_compile_one(parsed, target))
        if target.name not in used:
            used.append(target.name)

    return Filter(checks=tuple(checks), fields=tuple(used))


def _compile_one(expr: FilterExpr, field: FieldDef) -> Callable[[RecordRow], bool]:
    if expr.op in ("~", "~="):
        needle = expr.value.casefold()

        def contains(row: RecordRow) -> bool:
            return needle in display_value(row.values.get(field.name)).casefold()

        return contains

    expected = _coerce(field, expr)
    op = expr.op

    def compare(row: RecordRow) -> bool:
        actual = row.values.get(field.name)
        left, right = _comparable(actual, expected)
        if op in ("=", "=="):
            return bool(left == right)
        if op in ("!=", "<>"):
            return bool(left != right)
        if op == ">":
            return bool(left > right)
        if op == ">=":
            return bool(left >= right)
        if op == "<":
            return bool(left < right)
        if op == "<=":
            return bool(left <= right)
        raise QueryError(f"Unsupported operator {op!r}.")

    return compare


def _coerce(field: FieldDef, expr: FilterExpr) -> object:
    text = expr.value
    try:
        if field.type_code in (1, 5, 6):
            return int(text)
        if field.type_code == 2:
            return float(text)
        if field.type_code == 8:
            return Decimal(text)
    except (ValueError, InvalidOperation) as exc:
        raise QueryError(
            f"{text!r} is not a valid {field.type_name} value for {field.name}.",
            hint=f"Filter {field.name} with a numeric value, for example {field.name}=1000.",
        ) from exc
    return text.casefold()


def _comparable(actual: object, expected: object) -> tuple[Any, Any]:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold(), expected
    if isinstance(actual, Decimal) and isinstance(expected, Decimal):
        return actual, expected
    if actual is None:
        return "", expected
    return actual, expected
