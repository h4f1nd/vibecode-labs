# Clarion 2.x DAT format

> **Just want to use the app?** You do not need this page. Start with
> [README → Open your first table](../README.md#open-your-first-table) and
> [docs/USAGE.md](USAGE.md). This page documents the bytes for maintainers and
> anyone verifying an export.

This is the layout DOTDAT implements. It was derived from a local 37-table
reference set (not committed) and verified against the `.DBF` exports that ship
beside those tables. All integers are little-endian unless stated otherwise.

The layout is independent of Clarion Viewer: it comes from the files and the DBF
ground truth. Clarion Viewer was used only to confirm how values should be
displayed (the `format` column, key listing and date rendering). See
[CLAVIEW.md](CLAVIEW.md) for the feature comparison.

```
+----------------------+  offset 0, 85 bytes
| header               |
+----------------------+  offset 85
| field descriptors    |  27 bytes each, field_count of them
+----------------------+
| key definitions      |  19 bytes + 6 bytes per part, key_count of them
+----------------------+  data_offset
| record 1             |  record_length bytes
| record 2             |
| ...                  |
+----------------------+
```

`data_offset` is normally exactly the end of the key definitions. DOTDAT accepts
a larger offset (padding) but rejects one that points into the schema.

## Header (85 bytes)

| Offset | Size | Type | Field | Notes |
|---:|---:|---|---|---|
| 0x00 | 2 | uint16 | `signature` | `0x3343` for Clarion 2.x |
| 0x02 | 2 | uint16 | `attributes` | Observed `0x00A0`; not interpreted |
| 0x04 | 1 | uint8 | `key_count` | Number of key blocks |
| 0x05 | 4 | uint32 | `record_count` | Includes deleted records |
| 0x09 | 4 | uint32 | `deleted_count` | Header's deleted total |
| 0x0D | 2 | uint16 | `field_count` | Sanity range 1–4096 |
| 0x0F | 2 | uint16 | `picture_count` | Informational |
| 0x11 | 2 | uint16 | `array_count` | Informational |
| 0x13 | 2 | uint16 | `record_length` | 5-byte record header + payload |
| 0x15 | 4 | uint32 | `data_offset` | Absolute file offset of record 1 |
| 0x19 | 4 | uint32 | `logical_eof` | Observed equal to `record_count` |
| 0x1D | 4 | uint32 | `logical_bof` | Observed `1` |
| 0x21 | 4 | uint32 | `free_record` | Observed `0` |
| 0x25 | 12 | char[12] | `record_name` | NUL/space padded, e.g. `RECORD` |
| 0x31 | 12 | char[12] | `memo_name` | Empty in the reference set |
| 0x3D | 3 | char[3] | `file_prefix` | e.g. `TAB` |
| 0x40 | 3 | char[3] | `record_prefix` | Often empty |
| 0x43 | 2 | uint16 | `memo_length` | Informational |
| 0x45 | 2 | uint16 | `memo_width` | Informational |
| 0x47 | 4 | uint32 | `reserved` | Zero in the reference set |
| 0x4B | 4 | uint32 | `last_change_time` | Centiseconds since midnight |
| 0x4F | 4 | uint32 | `last_change_date` | Clarion day count |
| 0x53 | 2 | uint16 | `reserved2` | Zero in the reference set |

Struct forms:

```python
_HEADER      = struct.Struct("<HHBIIHHHHIIII")      # 37 bytes
_HEADER_TAIL = struct.Struct("<12s12s3s3sHHIIIH")   # 48 bytes
```

### Example header

```
signature        0x3343
attributes       0x00A0
key_count        5
record_count     over a million
deleted_count    0
field_count      12
record_length    44  (39-byte payload)
data_offset      606 (85 + 12*27 + 5*19 + 17*6)
last_change      a local timestamp, shown as YYYY-MM-DD HH:MM:SS
file_prefix      SMP
record_name      RECORD
```

## Field descriptor (27 bytes)

| Offset | Size | Type | Field | Notes |
|---:|---:|---|---|---|
| 0 | 1 | uint8 | `type_code` | See the type table |
| 1 | 16 | char[16] | `name` | Often `PREFIX:NAME` |
| 17 | 2 | uint16 | `offset` | Relative to the payload (record + 5) |
| 19 | 2 | uint16 | `length` | Bytes occupied by the value |
| 21 | 1 | uint8 | `significant` | Digits/precision hint |
| 22 | 1 | uint8 | `decimals` | Implied BCD fraction digits |
| 23 | 2 | uint16 | `array_number` | 0 for scalars |
| 25 | 2 | uint16 | `picture_number` | Informational |

Struct form:

```python
_FIELD = struct.Struct("<B16sHHBBHH")  # 27 bytes
```

Validation: for every field, `offset + length <= record_length - 5`. A field of
length zero is allowed and decodes to an empty value.

`significant` and `decimals` form the `format` string shown in the Structure tab
and by `dotdat info` (`13.0`, `9.2`, ...), which is the same column Clarion Viewer
prints. A field with `significant = 0` has no format string.

## Key definition

Each key starts with a 19-byte head, followed by `components` parts of 6 bytes.

```python
_KEY_HEAD = struct.Struct("<B16sBB")  # 19 bytes
_KEY_PART = struct.Struct("<BHHB")    # 6 bytes
```

Head:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 1 | `components` |
| 1 | 16 | `name` |
| 17 | 1 | `composite_type` |
| 18 | 1 | `composite_length` |

Part:

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 1 | `field_type` | Same codes as fields |
| 1 | 2 | `field_number` | 1-based index into the field list |
| 3 | 2 | `offset` | Offset inside the payload |
| 5 | 1 | `length` | Bytes in this key component |

Keys are displayed but not used for lookup. DOTDAT pages by physical record
index. The Structure tab prints `composite_type` as hex (`0x0030`), the same
key-type column Clarion Viewer shows. Clarion's `NOCASE` / `OPT` / `DUP` flag
names are not reconstructed, because the stored byte does not identify them
unambiguously.

Example key layout (offsets are shown in `--json`):

```
ACCOUNT_KEY   3 parts, 0x0030: ACCOUNT, DATE, TIME
DATE_KEY      2 parts, 0x0030: DATE, ACCOUNT
YEAR_KEY      5 parts, 0x0030: YEAR, MONTH, ACCOUNT, DATE, TIME
CODE_KEY      4 parts, 0x0030: YEAR, MONTH, CODE, DATE
TERMINAL_KEY  3 parts, 0x0030: PC, DATE, ACCOUNT
```

## Records

Every record occupies `record_length` bytes:

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 1 | `status` | Bit `0x10` = deleted |
| 1 | 4 | `pointer` | Physical/next pointer; observed `0` |
| 5 | N | payload | Field values at their declared offsets |

`payload_size = record_length - 5`. Field offsets are relative to the **start of
the payload**, not the record.

Status values observed: `0x01` (active), `0x05` (active, other flags), `0x11`
(deleted). Only the `0x10` bit decides deletion:

```python
deleted = bool(status & 0x10)
```

DOTDAT ignores the pointer and the free-record chain; deleted slots stay in
place. The last record must end at or before EOF:
`data_offset + record_count * record_length <= file_size`.

### Illustrative record

```
01 00 00 00 00 | <payload: ACCOUNT, REGION, DATE, MONTH, YEAR, ...>
status=0x01  pointer=0  ACCOUNT=1000000001  AREA="01"  DATE=73928 ...
```

Decoded:

| Field | Value |
|---|---|
| `ACCOUNT` | 1000000001 |
| `AREA` | `01` |
| `DATE` | 73928 (Clarion day) |
| `MONTH` | 5 |
| `YEAR` | 2003 |
| `CODE` | 1 |
| `PC` | `01` |
| `DK` | `K` |
| `TIME` | 360,000 (centiseconds) |
| `AMOUNT` | 2000.00 |
| `BALANCE` | 1234.56 |
| `SHARE` | empty |

The `TIME` value is the stored centisecond time, not an ISO clock string; DOTDAT
shows the raw field in the grid. The header's last-change timestamp is converted.

## Field types

| Code | Name | Decoding |
|---:|---|---|
| 1 | LONG | signed 32-bit integer |
| 2 | REAL | IEEE-754 double |
| 3 | STRING | fixed bytes, NUL-terminated, decoded with the selected code page |
| 4 | PICTURE | treated as STRING |
| 5 | BYTE | unsigned 8-bit |
| 6 | SHORT | signed 16-bit |
| 7 | GROUP | raw bytes |
| 8 | DECIMAL | packed BCD with implied decimals |

Only types **1, 3 and 8** occur in the 37-table reference set. The others have
best-effort decoders and no real-world fixture.

### Packed BCD (type 8)

For `length` bytes there are `2 * length` nibbles:

1. The high nibble of the first byte is the sign: `0`–`7` positive, `8`–`9`
   negative.
2. Every remaining nibble is a decimal digit.
3. The integer is divided by `10 ** decimals`.

Example, `BALANCE` = 1234.56, 6 bytes, 2 decimals:

```
bytes   00 00 00 12 34 56
nibbles 0|0 0|0 0|0 1|2 3|4 5|6
digits  000000123456  -> 123456
scaled  -2            -> 1234.56
```

Negative values set the first nibble to 8:

```
bytes   80 00 00 05 00 00  ->  -500.00  (6 bytes, 2 decimals)
```

A non-decimal nibble (10–15) after the sign raises a per-field invalid marker
instead of corrupting the row.

### Strings

The bytes are decoded with the chosen encoding (default CP437), cut at the first
NUL, and trailing spaces are removed. The reference data is DOS-era text; CP437
is the safe default. If a table contains Windows-1252 accents, choose that
encoding before opening.

Array fields (`array_number != 0`) render as hex because this format revision
does not expose element descriptors.

## Dates and times

`last_change_date`, `DATE` and similar values are day counts with the epoch
**1800-12-28**:

```
date = 1800-12-28 + days
```

Examples:

| Days | Date |
|---:|---|
| 0 | invalid / not recorded |
| 1 | 1800-12-29 |
| 73928 | 2003-05-26 |
| 82214 | 2026-01-31 |
| 82400 | 2026-08-05 |

`last_change_time` and `TIME` are centiseconds since midnight:

```
hours, rest = divmod(cs, 360000)
minutes, rest = divmod(rest, 6000)
seconds, hundredths = divmod(rest, 100)
```

`360,000` decomposes to `01:00:00.00`. The header timestamp is printed to
whole seconds (`2026-01-31 01:00:00`).

DOTDAT reads ordinary LONG fields as plain integers, because Clarion has no
date type: a date is a LONG plus a picture, and a `.DAT` written without
pictures carries no marker. `DatFile.date_fields()` samples up to 64 records
spread across the file. A LONG column is flagged only when at least 90% of its
non-zero samples fall between day 36,526 (1900-01-01) and day 109,573
(2100-12-31). With that guard, `DATE` is flagged while `TIME` (millions of
centiseconds) and small counters are not.

Flagged columns are listed in `info_dict()["date_fields"]`. The GUI may show
them as `YYYY-MM-DD`; the `dates` checkbox turns that off, the cell tooltip keeps
the stored number, and filters, `rows` output and every export always use the
raw integer. A column that fails the sample test is shown as a number
everywhere. Clarion Viewer renders the same date columns as dates; DOTDAT
follows that display rule and adds the toggle.

## Field-name prefixes

Descriptors store `SMP:ACCOUNT`, `REF:TYPE`, and so on. The prefix normally equals
the header `file_prefix`. DOTDAT strips it for display (`ACCOUNT`) and keeps
`raw_name`. Exports use the stripped name, matching the `.DBF` exports.

## Structural validation

DOTDAT opens a file only when all of these hold:

| Check | Failure |
|---|---|
| File at least 85 bytes | `TruncatedDatFile` |
| Signature `0x3343` | `NotADatFile` |
| `1 <= field_count <= 4096` | `CorruptDatFile` |
| `record_length >= 5` | `CorruptDatFile` |
| Every field fits the payload | `CorruptDatFile` |
| Descriptors and keys fit the file | `TruncatedDatFile` |
| `data_offset >= schema end` | `CorruptDatFile` |
| `data_offset <= file size` | `TruncatedDatFile` |
| `data_offset + record_count * record_length <= file size` | `TruncatedDatFile` |

`BROKEN.DAT` in the reference set is the canonical failure: its header claims 60,000
fields (0x2F51), which cannot fit the file. DOTDAT reports the count and asks for
a backup instead of guessing.

## Not implemented

- Clarion 3.x and later table layouts.
- TPS (TopSpeed) files and their index structures.
- `.MEM` memo bodies.
- Key-based lookup and index files (`.K01`).
- Writing, deleting, packing or repairing tables.
- Array element descriptors that this revision does not store.

## References

- [ARCHITECTURE.md](ARCHITECTURE.md) — how these bytes become pages and exports
- [USAGE.md](USAGE.md) — field naming and filters from a user's point of view
- [GLOSSARY.md](GLOSSARY.md) — terms
