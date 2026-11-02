"""Decoders for the three value families used by Clarion 2.x.

Only three types appear in the reference data set: LONG (1), STRING (3) and
packed BCD DECIMAL (8). The remaining legacy types are decoded best-effort so
a rare file still opens instead of crashing.
"""

from __future__ import annotations

import struct
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from .models import FieldDef

#: Clarion dates count days from this epoch.
CLARION_EPOCH = date(1800, 12, 28)

_LONG = struct.Struct("<i")
_REAL = struct.Struct("<d")
_SHORT = struct.Struct("<h")


def decode_decimal(raw: bytes, decimals: int) -> Decimal:
    """Decode Clarion packed BCD.

    The high nibble of the first byte is the sign (0-7 positive, 8-9
    negative); every remaining nibble is a decimal digit. ``decimals`` is the
    implied number of fractional digits.
    """
    if not raw:
        return Decimal(0)

    first = raw[0]
    sign = first >> 4
    value = first & 0x0F
    if value > 9:
        raise ValueError(f"invalid packed decimal: {raw.hex()}")

    for byte in raw[1:]:
        high = byte >> 4
        low = byte & 0x0F
        if high > 9 or low > 9:
            raise ValueError(f"invalid packed decimal: {raw.hex()}")
        value = value * 100 + high * 10 + low

    result = Decimal(value).scaleb(-decimals) if decimals else Decimal(value)
    return -result if sign >= 8 else result


def decode_string(raw: bytes, encoding: str) -> str:
    """Decode a fixed-width string and drop its NUL/space padding."""
    text = raw.split(b"\x00", 1)[0].decode(encoding, errors="replace")
    return text.rstrip(" ")


def decode_value(field: FieldDef, raw: bytes, encoding: str = "cp437") -> Any:
    """Decode one field value.

    Raises:
        ValueError: the bytes do not match the declared type.
    """
    if field.length == 0:
        return ""
    if field.array_number:
        # Arrays need element descriptors that this format does not expose in
        # the files we support. Keep the bytes so nothing is silently lost.
        return raw
    if field.type_code == 1:
        return _LONG.unpack_from(raw)[0]
    if field.type_code == 2:
        return _REAL.unpack_from(raw)[0]
    if field.type_code == 3 or field.type_code == 4:
        return decode_string(raw, encoding) if field.length else ""
    if field.type_code == 5:
        return raw[0]
    if field.type_code == 6:
        return _SHORT.unpack_from(raw)[0]
    if field.type_code == 8:
        return decode_decimal(raw, field.decimals)
    return raw


def display_value(value: Any) -> str:
    """Render a decoded value as text."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex(" ")
    return str(value)


def clarion_date(days: int) -> date | None:
    """Convert a Clarion day count to a date, or ``None`` when out of range."""
    if days <= 0:
        return None
    try:
        return CLARION_EPOCH + timedelta(days=days)
    except OverflowError:
        return None


def clarion_time(centiseconds: int) -> time | None:
    """Convert centiseconds since midnight to a time."""
    if centiseconds < 0 or centiseconds >= 86_400_00:
        return None
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    seconds, hundredths = divmod(rest, 100)
    return time(hours, minutes, seconds, hundredths * 10_000)


def format_clarion_timestamp(days: int, centiseconds: int) -> str:
    """Human readable timestamp used by ``info`` and the GUI overview."""
    if days <= 0 and centiseconds <= 0:
        return "not recorded"
    day = clarion_date(days)
    clock = clarion_time(centiseconds)
    if day is None and clock is None:
        return "not recorded"
    if day is None:
        return clock.strftime("%H:%M:%S") if clock else "not recorded"
    if clock is None:
        return day.isoformat()
    return datetime.combine(day, clock).isoformat(sep=" ", timespec="seconds")
