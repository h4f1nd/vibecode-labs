"""Immutable descriptions of a Clarion 2.x DAT table."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

FIELD_TYPE_NAMES: dict[int, str] = {
    1: "LONG",
    2: "REAL",
    3: "STRING",
    4: "PICTURE",
    5: "BYTE",
    6: "SHORT",
    7: "GROUP",
    8: "DECIMAL",
}


def field_type_name(code: int) -> str:
    """Return the Clarion type name for ``code``."""
    return FIELD_TYPE_NAMES.get(code, f"TYPE_{code}")


def json_value(value: Any) -> Any:
    """Convert a decoded value into something ``json.dumps`` accepts."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    return value


@dataclass(frozen=True, slots=True)
class FieldDef:
    """One 27-byte field descriptor.

    ``name`` is the display name with the Clarion file prefix removed
    (``SMP:ACCOUNT`` becomes ``ACCOUNT``). ``raw_name`` keeps the bytes as stored.
    """

    index: int
    name: str
    type_code: int
    offset: int
    length: int
    significant: int
    decimals: int
    array_number: int
    picture_number: int
    raw_name: str = ""

    @property
    def type_name(self) -> str:
        return field_type_name(self.type_code)

    @property
    def is_decimal(self) -> bool:
        return self.type_code == 8

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "raw_name": self.raw_name or self.name,
            "type_code": self.type_code,
            "type": self.type_name,
            "offset": self.offset,
            "length": self.length,
            "significant": self.significant,
            "decimals": self.decimals,
            "array_number": self.array_number,
            "picture_number": self.picture_number,
        }


@dataclass(frozen=True, slots=True)
class KeyPart:
    """One component of a key."""

    field_type: int
    field_number: int
    offset: int
    length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_type": self.field_type,
            "field_type_name": field_type_name(self.field_type),
            "field_number": self.field_number,
            "offset": self.offset,
            "length": self.length,
        }


@dataclass(frozen=True, slots=True)
class KeyDef:
    """One key definition stored after the field descriptors."""

    index: int
    name: str
    components: int
    composite_type: int
    composite_length: int
    parts: tuple[KeyPart, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "components": self.components,
            "composite_type": self.composite_type,
            "composite_length": self.composite_length,
            "parts": [part.to_dict() for part in self.parts],
        }


@dataclass(frozen=True, slots=True)
class DatHeader:
    """The fixed 85-byte file header."""

    signature: int
    attributes: int
    key_count: int
    record_count: int
    deleted_count: int
    field_count: int
    picture_count: int
    array_count: int
    record_length: int
    data_offset: int
    logical_eof: int
    logical_bof: int
    free_record: int
    record_name: str
    memo_name: str
    file_prefix: str
    record_prefix: str
    memo_length: int
    memo_width: int
    reserved: int
    last_change_time: int
    last_change_date: int
    reserved2: int

    @property
    def signature_hex(self) -> str:
        return f"0x{self.signature:04X}"

    @property
    def payload_size(self) -> int:
        """Bytes per record after the 5-byte record header."""
        return self.record_length - 5

    @property
    def active_count(self) -> int:
        return max(0, self.record_count - self.deleted_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "signature_hex": self.signature_hex,
            "attributes": self.attributes,
            "key_count": self.key_count,
            "record_count": self.record_count,
            "deleted_count": self.deleted_count,
            "active_count": self.active_count,
            "field_count": self.field_count,
            "picture_count": self.picture_count,
            "array_count": self.array_count,
            "record_length": self.record_length,
            "payload_size": self.payload_size,
            "data_offset": self.data_offset,
            "logical_eof": self.logical_eof,
            "logical_bof": self.logical_bof,
            "free_record": self.free_record,
            "record_name": self.record_name,
            "memo_name": self.memo_name,
            "file_prefix": self.file_prefix,
            "record_prefix": self.record_prefix,
            "memo_length": self.memo_length,
            "memo_width": self.memo_width,
            "reserved": self.reserved,
            "last_change_time": self.last_change_time,
            "last_change_date": self.last_change_date,
            "reserved2": self.reserved2,
        }


@dataclass(frozen=True, slots=True)
class RecordRow:
    """A decoded record."""

    index: int
    status: int
    deleted: bool
    values: dict[str, Any]

    @property
    def number(self) -> int:
        """1-based record number, as the GUI and CLI show it."""
        return self.index + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.number,
            "status": self.status,
            "deleted": self.deleted,
            "values": {name: json_value(value) for name, value in self.values.items()},
        }


@dataclass(frozen=True, slots=True)
class Page:
    """A slice of rows plus what is known about the total."""

    offset: int
    limit: int
    total: int | None
    rows: tuple[RecordRow, ...]

    @property
    def has_more(self) -> bool:
        if self.total is not None:
            return self.offset + len(self.rows) < self.total
        return len(self.rows) == self.limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "limit": self.limit,
            "total": self.total,
            "has_more": self.has_more,
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class TableInfo:
    """Everything the UI needs before reading records."""

    path: Path
    size: int
    encoding: str
    header: DatHeader
    fields: tuple[FieldDef, ...]
    keys: tuple[KeyDef, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "file_name": self.path.name,
            "size": self.size,
            "encoding": self.encoding,
            "header": self.header.to_dict(),
            "fields": [field.to_dict() for field in self.fields],
            "keys": [key.to_dict() for key in self.keys],
        }
