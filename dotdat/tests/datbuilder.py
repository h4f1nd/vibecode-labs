"""Build synthetic Clarion 2.x DAT files for the test suite.

The layout here mirrors the real files byte for byte: an 85-byte header, 27-byte
field descriptors, optional key blocks, and records made of a 5-byte header plus
the field payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

SIGNATURE = 0x3343

HEADER = struct.Struct("<HHBIIHHHHIIII")
HEADER_TAIL = struct.Struct("<12s12s3s3sHHIIIH")
HEADER_SIZE = HEADER.size + HEADER_TAIL.size
FIELD = struct.Struct("<B16sHHBBHH")
KEY_HEAD = struct.Struct("<B16sBB")
KEY_PART = struct.Struct("<BHHB")


@dataclass
class FieldSpec:
    name: str
    type_code: int
    length: int
    decimals: int = 0
    significant: int = 0
    array_number: int = 0
    picture_number: int = 0
    offset: int | None = None


@dataclass
class KeySpec:
    name: str
    parts: list[tuple[int, int, int, int]] = field(default_factory=list)
    composite_type: int = 0
    composite_length: int = 0


def encode_decimal(value: Any, length: int, decimals: int) -> bytes:
    """Encode a value as Clarion packed BCD."""
    scaled = int(Decimal(str(value)).scaleb(decimals))
    negative = scaled < 0
    digits = str(abs(scaled)).zfill(2 * length - 1)
    if len(digits) > 2 * length - 1:
        raise ValueError(f"{value} does not fit in {length} BCD bytes")
    nibbles = [8 if negative else 0, *(int(char) for char in digits)]
    return bytes((nibbles[index] << 4) | nibbles[index + 1] for index in range(0, 2 * length, 2))


def encode_value(spec: FieldSpec, value: Any) -> bytes:
    if spec.array_number:
        raw = bytes(value)
        if len(raw) != spec.length:
            raise ValueError(f"array {spec.name} needs {spec.length} bytes")
        return raw
    if spec.type_code == 1:
        return struct.pack("<i", int(value))
    if spec.type_code == 2:
        return struct.pack("<d", float(value))
    if spec.type_code in (3, 4):
        raw = str(value).encode("cp437")
        if len(raw) > spec.length:
            raise ValueError(f"{value!r} is longer than {spec.name}")
        return raw.ljust(spec.length, b"\x00")
    if spec.type_code == 5:
        return struct.pack("<B", int(value))
    if spec.type_code == 6:
        return struct.pack("<h", int(value))
    if spec.type_code == 8:
        return encode_decimal(value, spec.length, spec.decimals)
    if isinstance(value, bytes):
        return value
    raise ValueError(f"cannot encode field type {spec.type_code}")


def build_bytes(
    fields: list[FieldSpec],
    rows: list[dict[str, Any]],
    *,
    keys: list[KeySpec] | None = None,
    statuses: list[int] | None = None,
    deleted: list[bool] | None = None,
    record_name: str = "RECORD",
    memo_name: str = "",
    file_prefix: str = "TST",
    record_prefix: str = "",
    attributes: int = 0x00A0,
    last_change_time: int = 360_000,
    last_change_date: int = 82_214,
    signature: int = SIGNATURE,
    field_count: int | None = None,
    key_count: int | None = None,
    record_count: int | None = None,
    deleted_count: int | None = None,
    record_length: int | None = None,
    data_offset: int | None = None,
    payload_size: int | None = None,
    truncate: int | None = None,
) -> bytes:
    """Serialize a complete table and return its bytes."""
    keys = keys or []
    if statuses is None:
        flags = deleted or [False] * len(rows)
        statuses = [0x11 if flag else 0x01 for flag in flags]
    if len(statuses) != len(rows):
        raise ValueError("statuses and rows must line up")

    offsets: list[int] = []
    cursor = 0
    for spec in fields:
        offsets.append(cursor if spec.offset is None else spec.offset)
        cursor = max(cursor, offsets[-1] + spec.length)

    payload = payload_size if payload_size is not None else cursor
    length = record_length if record_length is not None else payload + 5
    schema_end = HEADER_SIZE + len(fields) * FIELD.size
    for key in keys:
        schema_end += KEY_HEAD.size + len(key.parts) * KEY_PART.size
    start = data_offset if data_offset is not None else schema_end

    count = record_count if record_count is not None else len(rows)
    gone = deleted_count
    if gone is None:
        gone = sum(1 for status in statuses if status & 0x10)

    chunks = [
        HEADER.pack(
            signature,
            attributes,
            key_count if key_count is not None else len(keys),
            count,
            gone,
            field_count if field_count is not None else len(fields),
            0,
            0,
            length,
            start,
            count,
            1,
            0,
        ),
        HEADER_TAIL.pack(
            record_name.encode("latin-1")[:12],
            memo_name.encode("latin-1")[:12],
            file_prefix.encode("latin-1")[:3],
            record_prefix.encode("latin-1")[:3],
            0,
            0,
            0,
            last_change_time,
            last_change_date,
            0,
        ),
    ]

    for spec, offset in zip(fields, offsets, strict=True):
        chunks.append(
            FIELD.pack(
                spec.type_code,
                spec.name.encode("latin-1")[:16],
                offset,
                spec.length,
                spec.significant,
                spec.decimals,
                spec.array_number,
                spec.picture_number,
            )
        )

    for key in keys:
        chunks.append(
            KEY_HEAD.pack(
                len(key.parts),
                key.name.encode("latin-1")[:16],
                key.composite_type,
                key.composite_length,
            )
        )
        for part in key.parts:
            chunks.append(KEY_PART.pack(*part))

    for status, row in zip(statuses, rows, strict=True):
        body = bytearray()
        for spec in fields:
            body += encode_value(spec, row.get(spec.name.split(":")[-1], row.get(spec.name)))
        if len(body) != payload:
            raise ValueError(f"payload is {len(body)} bytes, header says {payload}")
        chunks.append(bytes((status,)) + b"\x00\x00\x00\x00" + bytes(body))

    data = b"".join(chunks)
    if truncate is not None:
        data = data[:truncate]
    return data


def write_dat(path: Path, *args: Any, **kwargs: Any) -> Path:
    path.write_bytes(build_bytes(*args, **kwargs))
    return path


SAMPLE_FIELDS = [
    FieldSpec("TST:ID", 1, 4),
    FieldSpec("TST:NAME", 3, 10),
    FieldSpec("TST:AMOUNT", 8, 6, decimals=2),
    FieldSpec("TST:FLAG", 3, 1),
]

SAMPLE_KEY = KeySpec("ID_KEY", [(1, 1, 0, 4)])

SAMPLE_ROWS = [
    {"ID": 1, "NAME": "ALPHA", "AMOUNT": "12.34", "FLAG": "A"},
    {"ID": 2, "NAME": "beta", "AMOUNT": "-5.00", "FLAG": "B"},
    {"ID": 3, "NAME": "Gamma", "AMOUNT": "0.00", "FLAG": "C"},
    {"ID": 4, "NAME": "DELETED", "AMOUNT": "99.99", "FLAG": "D"},
]


def write_sample(path: Path, **overrides: Any) -> Path:
    options: dict[str, Any] = {
        "keys": [SAMPLE_KEY],
        "deleted": [False, False, False, True],
    }
    options.update(overrides)
    return write_dat(path, SAMPLE_FIELDS, SAMPLE_ROWS, **options)
