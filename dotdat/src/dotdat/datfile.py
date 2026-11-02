"""Read-only access to a Clarion 2.x ``.DAT`` table.

The layout implemented here was verified against the ``.DBF`` exports that
ship beside the reference data (``SAMPLE.DBF``, ``LEDGER.DBF``) and against the
deleted-record count in ``JOURNAL.DAT``.
"""

from __future__ import annotations

import codecs
import mmap
import os
import struct
from collections.abc import Callable, Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import codec
from .errors import (
    CorruptDatFile,
    DotDatError,
    NotADatFile,
    QueryError,
    TruncatedDatFile,
)
from .models import DatHeader, FieldDef, KeyDef, KeyPart, Page, RecordRow, TableInfo

SIGNATURE = 0x3343
DELETED_FLAG = 0x10
HEADER_SIZE = 85

# Clarion has no date type: a date is a LONG holding days since 1800-12-28.
# These bounds keep the display hint away from counters, amounts and ids that
# only happen to be small numbers.
DATE_WINDOW = (36_526, 109_573)  # 1900-01-01 .. 2100-12-31
DATE_SAMPLES = 64
DATE_MIN_SAMPLES = 1
DATE_RATIO = 0.9

_HEADER = struct.Struct("<HHBIIHHHHIIII")
_HEADER_TAIL = struct.Struct("<12s12s3s3sHHIIIH")
_FIELD = struct.Struct("<B16sHHBBHH")
_KEY_HEAD = struct.Struct("<B16sBB")
_KEY_PART = struct.Struct("<BHHB")


def _name(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin1", errors="replace").strip()


def _strip_prefix(name: str, prefix: str) -> str:
    """Drop ``PREFIX:`` from a Clarion field name for display."""
    if prefix and name.casefold().startswith(prefix.casefold() + ":"):
        return name[len(prefix) + 1 :] or name
    return name


class DatFile:
    """An open DAT file. Always read-only; the constructor never writes."""

    def __init__(self, path: Path, encoding: str = "cp437") -> None:
        try:
            codecs.lookup(encoding)
        except LookupError as exc:
            raise DotDatError(
                f"Unknown text encoding {encoding!r}.",
                hint="Use a Python codec name such as cp437, cp850, cp1252 or latin-1.",
            ) from exc
        self.path = path
        self.encoding = encoding
        self._date_fields: tuple[str, ...] | None = None
        self._fh = path.open("rb")
        try:
            self.size = os.fstat(self._fh.fileno()).st_size
            if self.size < HEADER_SIZE:
                raise TruncatedDatFile(
                    f"{path.name} is only {self.size} bytes; a DAT header needs {HEADER_SIZE}.",
                    hint="The file is empty or not a Clarion DAT file.",
                )
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self._fh.close()
            raise

        try:
            self._parse()
        except Exception:
            self._mm.close()
            self._fh.close()
            raise

    # ------------------------------------------------------------------ parse

    def _parse(self) -> None:
        data = self._mm
        try:
            (
                signature,
                attributes,
                key_count,
                record_count,
                deleted_count,
                field_count,
                picture_count,
                array_count,
                record_length,
                data_offset,
                logical_eof,
                logical_bof,
                free_record,
            ) = _HEADER.unpack_from(data, 0)
            (
                record_name,
                memo_name,
                file_prefix,
                record_prefix,
                memo_length,
                memo_width,
                reserved,
                last_change_time,
                last_change_date,
                reserved2,
            ) = _HEADER_TAIL.unpack_from(data, _HEADER.size)
        except struct.error as exc:
            raise TruncatedDatFile(
                f"{self.path.name} has an incomplete header.",
                hint="The file is shorter than the 85-byte Clarion DAT header.",
            ) from exc

        if signature != SIGNATURE:
            raise NotADatFile(
                f"{self.path.name} is not a Clarion 2.x DAT file "
                f"(signature {signature:#06x}, expected {SIGNATURE:#06x}).",
                hint="DOTDAT reads legacy Clarion 2.x .DAT tables, not TPS or dBase files.",
            )
        if field_count < 1 or field_count > 4096:
            raise CorruptDatFile(
                f"{self.path.name} declares {field_count} fields; that is not plausible.",
                hint="The header is damaged. Restore the file from a backup.",
            )
        if record_length < 5:
            raise CorruptDatFile(
                f"{self.path.name} declares a {record_length}-byte record; the minimum is 5.",
                hint="The header is damaged. Restore the file from a backup.",
            )

        self.header = DatHeader(
            signature=signature,
            attributes=attributes,
            key_count=key_count,
            record_count=record_count,
            deleted_count=deleted_count,
            field_count=field_count,
            picture_count=picture_count,
            array_count=array_count,
            record_length=record_length,
            data_offset=data_offset,
            logical_eof=logical_eof,
            logical_bof=logical_bof,
            free_record=free_record,
            record_name=_name(record_name),
            memo_name=_name(memo_name),
            file_prefix=_name(file_prefix),
            record_prefix=_name(record_prefix),
            memo_length=memo_length,
            memo_width=memo_width,
            reserved=reserved,
            last_change_time=last_change_time,
            last_change_date=last_change_date,
            reserved2=reserved2,
        )

        fields: list[FieldDef] = []
        pos = HEADER_SIZE
        for index in range(field_count):
            if pos + _FIELD.size > self.size:
                raise TruncatedDatFile(
                    f"{self.path.name} ends inside field descriptor {index + 1}.",
                    hint="The file is truncated. Restore it from a backup.",
                )
            type_code, raw_name, offset, length, significant, decimals, array, picture = (
                _FIELD.unpack_from(data, pos)
            )
            full_name = _name(raw_name) or f"FIELD_{index + 1}"
            fields.append(
                FieldDef(
                    index=index + 1,
                    name=_strip_prefix(full_name, self.header.file_prefix),
                    raw_name=full_name,
                    type_code=type_code,
                    offset=offset,
                    length=length,
                    significant=significant,
                    decimals=decimals,
                    array_number=array,
                    picture_number=picture,
                )
            )
            pos += _FIELD.size

        payload = record_length - 5
        for field in fields:
            if field.length == 0:
                continue
            if field.offset + field.length > payload:
                raise CorruptDatFile(
                    f"{self.path.name}: field {field.name} ({field.offset}+{field.length}) "
                    f"does not fit in the {payload}-byte record payload.",
                    hint="The header and field descriptors disagree. Restore the file.",
                )

        keys: list[KeyDef] = []
        for key_index in range(key_count):
            if pos + _KEY_HEAD.size > self.size:
                raise TruncatedDatFile(
                    f"{self.path.name} ends inside key definition {key_index + 1}.",
                    hint="The file is truncated. Restore it from a backup.",
                )
            components, raw_name, composite_type, composite_length = _KEY_HEAD.unpack_from(data, pos)
            pos += _KEY_HEAD.size
            if pos + components * _KEY_PART.size > self.size:
                raise TruncatedDatFile(
                    f"{self.path.name} ends inside the parts of key {_name(raw_name)!r}.",
                    hint="The file is truncated. Restore it from a backup.",
                )
            parts: list[KeyPart] = []
            for _ in range(components):
                field_type, field_number, offset, length = _KEY_PART.unpack_from(data, pos)
                parts.append(
                    KeyPart(
                        field_type=field_type,
                        field_number=field_number,
                        offset=offset,
                        length=length,
                    )
                )
                pos += _KEY_PART.size
            keys.append(
                KeyDef(
                    index=key_index + 1,
                    name=_name(raw_name) or f"KEY_{key_index + 1}",
                    components=components,
                    composite_type=composite_type,
                    composite_length=composite_length,
                    parts=tuple(parts),
                )
            )

        if data_offset < pos:
            raise CorruptDatFile(
                f"{self.path.name}: data starts at {data_offset}, before the schema ends at {pos}.",
                hint="The header is damaged. Restore the file from a backup.",
            )
        if data_offset > self.size:
            raise TruncatedDatFile(
                f"{self.path.name}: data starts at {data_offset}, beyond the {self.size}-byte file.",
                hint="The file is truncated. Restore it from a backup.",
            )

        expected_end = data_offset + record_count * record_length
        if expected_end > self.size:
            raise TruncatedDatFile(
                f"{self.path.name} declares {record_count:,} records "
                f"({expected_end:,} bytes) but is only {self.size:,} bytes.",
                hint="The file is truncated. Restore it from a backup.",
            )

        self.fields = tuple(fields)
        self.keys = tuple(keys)
        self.payload_size = payload

    # ------------------------------------------------------------------ access

    def resolve_field(self, name: str) -> FieldDef:
        """Find a field by name, case-insensitively.

        Both the display name and the raw ``PREFIX:NAME`` spelling work.
        """
        wanted = name.casefold()
        for field in self.fields:
            if field.name.casefold() == wanted or field.raw_name.casefold() == wanted:
                return field
        names = ", ".join(field.name for field in self.fields[:12])
        if len(self.fields) > 12:
            names += ", ..."
        raise QueryError(
            f"Unknown field {name!r}.",
            hint=f"Available fields: {names}",
        )

    def read_record(
        self,
        index: int,
        fields: Sequence[FieldDef] | None = None,
    ) -> RecordRow:
        """Decode record ``index`` (0-based).

        ``fields`` limits decoding to the given descriptors. The predicate
        fast path uses it to read only the columns a filter touches.
        """
        if index < 0 or index >= self.header.record_count:
            raise IndexError(f"record {index} is outside 0..{self.header.record_count - 1}")
        base = self.header.data_offset + index * self.header.record_length
        status = self._mm[base]
        deleted = bool(status & DELETED_FLAG)
        values: dict[str, Any] = {}
        payload = base + 5
        for field in fields if fields is not None else self.fields:
            start = payload + field.offset
            raw = self._mm[start : start + field.length]
            try:
                values[field.name] = codec.decode_value(field, raw, self.encoding)
            except (ValueError, struct.error):
                values[field.name] = f"<invalid:{raw.hex()}>"
        return RecordRow(index=index, status=status, deleted=deleted, values=values)

    def _filter_fields(
        self,
        predicate: Callable[[RecordRow], bool] | None,
    ) -> list[FieldDef] | None:
        """Resolve the field list attached to a :class:`query.Filter`."""
        if predicate is None:
            return None
        names: tuple[str, ...] | None = getattr(predicate, "fields", None)
        if not names:
            return None
        return [self.resolve_field(name) for name in names]

    def _iter_plain(
        self,
        include_deleted: bool,
        start: int,
        predicate: Callable[[RecordRow], bool] | None,
    ) -> Iterator[RecordRow]:
        index = max(0, start)
        total = self.header.record_count
        filter_fields = self._filter_fields(predicate)
        while index < total:
            if predicate is not None and filter_fields is not None:
                partial = self.read_record(index, fields=filter_fields)
                index += 1
                if not include_deleted and partial.deleted:
                    continue
                if not predicate(partial):
                    continue
                yield self.read_record(index - 1)
                continue
            row = self.read_record(index)
            index += 1
            if not include_deleted and row.deleted:
                continue
            if predicate is not None and not predicate(row):
                continue
            yield row

    def iter_records(
        self,
        include_deleted: bool = False,
        start: int = 0,
        predicate: Callable[[RecordRow], bool] | None = None,
        sort: str | None = None,
        desc: bool = False,
    ) -> Iterator[RecordRow]:
        """Yield records in file order, or sorted when ``sort`` is set.

        Sorting materialises every matching row. That is fine for a filtered
        export but expensive on a 1.4 million row table; the GUI warns about it.
        """
        if sort is None:
            yield from self._iter_plain(include_deleted, start, predicate)
            return

        field = self.resolve_field(sort)
        rows = list(self._iter_plain(include_deleted, start, predicate))
        rows.sort(key=lambda row: _sort_key(row.values.get(field.name)), reverse=desc)
        yield from rows

    def page(
        self,
        offset: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
        predicate: Callable[[RecordRow], bool] | None = None,
        sort: str | None = None,
        desc: bool = False,
    ) -> Page:
        """Return one page of rows, applying the deleted filter and predicate."""
        if offset < 0:
            raise QueryError("Offset cannot be negative.")
        if limit < 1 or limit > 10_000:
            raise QueryError(
                f"Page size {limit} is outside 1..10000.",
                hint="Use a page size between 1 and 10000 rows.",
            )

        if sort is not None:
            materialised = list(
                self.iter_records(
                    include_deleted=include_deleted,
                    predicate=predicate,
                    sort=sort,
                    desc=desc,
                )
            )
            total: int | None = len(materialised)
            selected = tuple(materialised[offset : offset + limit])
            return Page(offset=offset, limit=limit, total=total, rows=selected)

        rows: tuple[RecordRow, ...]
        if predicate is None:
            total = (
                self.header.record_count
                if include_deleted
                else self.header.active_count
            )
            if include_deleted or self.header.deleted_count == 0:
                stop = min(offset + limit, self.header.record_count)
                rows = tuple(self.read_record(i) for i in range(offset, stop))
            else:
                rows = tuple(_take(self.iter_records(include_deleted=False), offset, limit))
            return Page(offset=offset, limit=limit, total=total, rows=rows)

        rows = tuple(_take(self.iter_records(include_deleted, predicate=predicate), offset, limit))
        return Page(offset=offset, limit=limit, total=None, rows=rows)

    def count(
        self,
        include_deleted: bool = False,
        predicate: Callable[[RecordRow], bool] | None = None,
    ) -> int:
        """Count matching rows, scanning when a predicate is present."""
        if predicate is None and not include_deleted:
            return self.header.active_count
        if predicate is None:
            return sum(1 for _ in self.iter_records(include_deleted))
        filter_fields = self._filter_fields(predicate)
        if filter_fields is not None:
            total = 0
            for index in range(self.header.record_count):
                partial = self.read_record(index, fields=filter_fields)
                if not include_deleted and partial.deleted:
                    continue
                if predicate(partial):
                    total += 1
            return total
        return sum(1 for _ in self.iter_records(include_deleted, predicate=predicate))

    def info(self) -> TableInfo:
        return TableInfo(
            path=self.path,
            size=self.size,
            encoding=self.encoding,
            header=self.header,
            fields=self.fields,
            keys=self.keys,
        )

    def date_fields(self) -> tuple[str, ...]:
        """LONG fields whose values look like Clarion day counts.

        Clarion stores dates as a LONG plus a picture. Files written without
        pictures carry no type marker, so the only safe signal left is the
        values themselves. A handful of records spread across the file are
        sampled; a column qualifies when at least 90% of its non-zero samples
        land between 1900 and 2100. Everything else stays a plain number.
        """
        if self._date_fields is not None:
            return self._date_fields

        longs = [field for field in self.fields if field.type_code == 1]
        found: list[str] = []
        total = self.header.record_count
        if longs and total:
            step = max(1, total // DATE_SAMPLES)
            indexes = list(range(0, total, step))[:DATE_SAMPLES]
            samples: dict[str, list[int]] = {field.name: [] for field in longs}
            for index in indexes:
                row = self.read_record(index, fields=longs)
                for field in longs:
                    value = row.values.get(field.name)
                    if isinstance(value, int) and value:
                        samples[field.name].append(value)
            low, high = DATE_WINDOW
            for field in longs:
                values = samples[field.name]
                if len(values) < DATE_MIN_SAMPLES:
                    continue
                inside = sum(1 for value in values if low <= value <= high)
                if inside / len(values) >= DATE_RATIO:
                    found.append(field.name)

        self._date_fields = tuple(found)
        return self._date_fields

    def info_dict(self) -> dict[str, Any]:
        data = self.info().to_dict()
        data["last_change"] = codec.format_clarion_timestamp(
            self.header.last_change_date,
            self.header.last_change_time,
        )
        data["date_fields"] = list(self.date_fields())
        return data

    # ------------------------------------------------------------------ close

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            self._mm.close()
        finally:
            self._fh.close()

    def __enter__(self) -> DatFile:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"DatFile({self.path.name!r}, records={self.header.record_count}, "
            f"fields={len(self.fields)})"
        )


def _sort_key(value: Any) -> tuple[int, Any]:
    if value is None:
        return (2, "")
    if isinstance(value, (Decimal, int, str, bytes)):
        return (0, value)
    return (1, str(value))


def _take(rows: Iterator[RecordRow], offset: int, limit: int) -> list[RecordRow]:
    skipped = 0
    taken: list[RecordRow] = []
    for row in rows:
        if skipped < offset:
            skipped += 1
            continue
        taken.append(row)
        if len(taken) >= limit:
            break
    return taken
