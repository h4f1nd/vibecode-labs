# Glossary

## Everyday terms

| Term | Plain meaning |
|---|---|
| **Table** | One `.DAT` file. You open one table at a time. |
| **Row** or **record** | One entry in the table, such as one transaction. |
| **Column** or **field** | One kind of value in every row, such as `ACCOUNT` or `BALANCE`. |
| **Active row** | A row that is not marked deleted. |
| **Deleted row** | A row whose deleted bit is set. It stays in the file; DOTDAT hides it unless you tick **deleted**. |
| **Filter** | A short condition that limits which rows you see, such as `AREA=01`. |
| **Export** | Saving the rows to a new file such as CSV or Excel. The source table is not changed. |
| **Read-only** | DOTDAT can look, but it cannot change the original file. |
| **Clarion Viewer** | The commercial Windows program whose read-only browser DOTDAT copies. |
| **Functional copy** | A new program that reproduces another program's behaviour without using its code or assets. |

## Technical terms

**BCD (binary-coded decimal)**
Clarion stores `DECIMAL` values as packed decimal nibbles, not IEEE floats. The
first nibble is the sign, the rest are digits, and the field descriptor supplies
the implied decimal places.

**Clarion**
A family of development tools and databases. DOTDAT reads the legacy 2.x `.DAT`
table format only.

**Clarion day**
A date stored as the number of days since 1800-12-28. Day 0 is treated as "not
recorded".

**Centisecond**
One hundredth of a second. Clarion stores times as centiseconds since midnight.

**Composite key / key part**
A key definition lists components, each pointing at a field number, offset and
length. The reference tables use composite keys, but DOTDAT only displays them;
it pages by physical record order.

**Format string**
The `significant.decimals` pair from a field descriptor, shown as `13.0` or
`9.2` in the Structure tab and `dotdat info`. It is the same format column
Clarion Viewer prints.

**Key type (`0x0030`)**
The raw `composite_type` byte from a key head, printed in hex. DOTDAT shows the
factual value instead of guessing Clarion's `NOCASE` / `OPT` / `DUP` labels.

**Parity**
How closely DOTDAT's views, columns and formatting match Clarion Viewer. The
full comparison is in [CLAVIEW.md](CLAVIEW.md).

**Reverse engineering (black box)**
Learning how a program behaves by running it and observing what it displays,
without reading its source or decompiling it. This is how DOTDAT's Clarion
Viewer parity was produced.

**DAT**
The table file DOTDAT opens. In this project it always means a Clarion 2.x
table, not a generic data file.

**Data offset**
Absolute byte offset in the file where the first record starts. It follows the
header, field descriptors and key definitions.

**DBF**
dBase file. The reference folder includes DBF exports used as ground truth for
verifying decoded values. DOTDAT does not read DBF.

**CSV**
Comma-separated values. A plain text table that Excel, LibreOffice and databases
can open. DOTDAT writes UTF-8 with a header row.

**Deleted flag**
Bit `0x10` in the first byte of a record. Its presence means the record is
deleted. Other status bits are not deletion.

**Encoding**
The code page used to turn stored bytes into text. The reference tables use
`cp437`; `cp1252` is a common alternative for Western text.

**Field descriptor**
The 27-byte record describing one field: type, name, payload offset, length,
significant digits, decimals, array number and picture number.

**File prefix**
Up to three characters stored in the header, usually also the prefix in field
names (`SMP:ACCOUNT`). DOTDAT strips it for display.

**Free record / pointer**
A 4-byte value after the status byte, and a header field for the free-list head.
DOTDAT ignores both; it reads records by physical index.

**Header**
The fixed 85-byte block at the start of a Clarion 2.x DAT file.

**JSONL**
JSON Lines: one JSON object per line. Easier to stream than one large JSON array.

**LONG**
A signed 32-bit little-endian integer.

**mmap**
Memory-mapped file access. DOTDAT maps the source read-only so opening a large
table does not load it into Python memory.

**Page**
A slice of rows returned by `DatFile.page`, with the best-known total and a
`has_more` flag.

**Payload**
The bytes after the 5-byte record header. `payload_size = record_length - 5`.
Field offsets are relative to the payload.

**Picture**
A legacy display format descriptor. DOTDAT treats type 4 (`PICTURE`) as a string
and does not apply the picture mask.

**Predicate**
A compiled filter closure that returns true or false for a `RecordRow`.

**Record**
One row: status byte, 4-byte pointer, then the fixed-length payload.

**Record length**
Total bytes per record, including the 5-byte header.

**Sign nibble**
The high nibble of the first BCD byte. 0–7 is positive, 8–9 negative.

**Status byte**
The first byte of a record. `0x01` active, `0x05` active with other flags,
`0x11` deleted in the reference data. Only `0x10` matters for deletion.

**TPS**
TopSpeed database files, a later Clarion format. Out of scope for v1.

**Trial cap**
The 100-record limit in the unregistered Clarion Viewer build used for the
comparison. DOTDAT shows the full table and has no cap.

**WebView2**
The Microsoft Edge runtime used by pywebview on Windows to render the GUI.

**XLSX**
An Excel workbook. DOTDAT writes one worksheet and is limited to 1,048,576 rows
including the header.
