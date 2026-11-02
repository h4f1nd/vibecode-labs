"""Streaming exporters.

Every writer is atomic: output goes to a temporary file in the destination
directory and is renamed only after the last row is written. A failed or
cancelled export never leaves a half-written file behind.
"""

from __future__ import annotations

import contextlib
import csv
import json
import os
from collections.abc import Callable, Iterable, Sequence
from html import escape as html_escape
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from .codec import display_value
from .datfile import DatFile
from .errors import ExportError, OutputExistsError, QueryError
from .models import FieldDef, RecordRow

EXPORT_FORMATS = ("csv", "txt", "json", "jsonl", "html", "xml", "sql", "xlsx")

EXTENSIONS: dict[str, str] = {
    "csv": ".csv",
    "txt": ".txt",
    "json": ".json",
    "jsonl": ".jsonl",
    "html": ".html",
    "xml": ".xml",
    "sql": ".sql",
    "xlsx": ".xlsx",
}

ProgressCallback = Callable[[int, int | None], None]
CancelCallback = Callable[[], bool]

_EXCEL_MAX_ROWS = 1_048_576


def select_fields(table: DatFile, names: Sequence[str] | None) -> list[FieldDef]:
    """Resolve an optional field list, rejecting unknown names."""
    if not names:
        return list(table.fields)
    selected: list[FieldDef] = []
    seen: set[str] = set()
    for name in names:
        field = table.resolve_field(name.strip())
        if field.name not in seen:
            selected.append(field)
            seen.add(field.name)
    if not selected:
        raise QueryError("No fields selected for export.")
    return selected


def export_table(
    table: DatFile,
    out: Path,
    fmt: str,
    *,
    include_deleted: bool = False,
    predicate: Callable[[RecordRow], bool] | None = None,
    fields: Sequence[str] | None = None,
    sort: str | None = None,
    desc: bool = False,
    force: bool = False,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
) -> int:
    """Write ``table`` to ``out`` and return the number of data rows written."""
    fmt = fmt.casefold()
    if fmt not in EXPORT_FORMATS:
        raise ExportError(
            f"Unknown export format {fmt!r}.",
            hint=f"Choose one of: {', '.join(EXPORT_FORMATS)}.",
        )
    if _same_file(table.path, out):
        raise ExportError(
            "Refusing to overwrite the source DAT file.",
            hint="Choose a different output name.",
        )
    if out.exists() and not force:
        raise OutputExistsError(
            f"{out} already exists.",
            hint="Pass --force to overwrite it, or choose another path.",
        )

    selected = select_fields(table, fields)
    total = _known_total(table, include_deleted, predicate, sort)
    if fmt == "xlsx" and total is not None and total > _EXCEL_MAX_ROWS - 1:
        raise ExportError(
            f"{total:,} rows exceed Excel's {_EXCEL_MAX_ROWS:,}-row limit.",
            hint="Use CSV, JSONL or SQL, which have no row cap.",
        )
    if cancel is not None and cancel():
        raise ExportError("Export cancelled.", hint="No output file was written.")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")

    try:
        rows = _iter_with_control(
            table,
            include_deleted=include_deleted,
            predicate=predicate,
            sort=sort,
            desc=desc,
            cancel=cancel,
        )
        if fmt == "xlsx":
            count = _write_xlsx(tmp, table, selected, rows, progress, total)
        else:
            with tmp.open("w", encoding="utf-8", newline="") as handle:
                count = _write_text(handle, fmt, table, selected, rows, progress, total)
        os.replace(tmp, out)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ExportError(
            f"Cannot write {out}: {exc.strerror or exc}",
            hint="Choose another folder, check free space, or close the file in another app.",
        ) from exc
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return count


def _same_file(source: Path, target: Path) -> bool:
    """Case-insensitive, link-aware comparison of the source and destination."""
    source_path = source.resolve()
    target_path = target.resolve()
    if os.path.normcase(str(source_path)) == os.path.normcase(str(target_path)):
        return True
    try:
        return target_path.exists() and os.path.samefile(source_path, target_path)
    except OSError:
        return False


def _known_total(
    table: DatFile,
    include_deleted: bool,
    predicate: Callable[[RecordRow], bool] | None,
    sort: str | None,
) -> int | None:
    if predicate is not None or sort is not None:
        return None
    return table.header.record_count if include_deleted else table.header.active_count


def _iter_with_control(
    table: DatFile,
    *,
    include_deleted: bool,
    predicate: Callable[[RecordRow], bool] | None,
    sort: str | None,
    desc: bool,
    cancel: CancelCallback | None,
) -> Iterable[RecordRow]:
    for row in table.iter_records(
        include_deleted=include_deleted,
        predicate=predicate,
        sort=sort,
        desc=desc,
    ):
        if cancel is not None and cancel():
            raise ExportError("Export cancelled.", hint="No output file was written.")
        yield row


def _write_text(
    handle: Any,
    fmt: str,
    table: DatFile,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    if fmt == "csv":
        return _write_delimited(handle, fields, rows, ",", progress, total)
    if fmt == "txt":
        return _write_delimited(handle, fields, rows, "\t", progress, total)
    if fmt == "json":
        return _write_json(handle, fields, rows, progress, total)
    if fmt == "jsonl":
        return _write_jsonl(handle, fields, rows, progress, total)
    if fmt == "html":
        return _write_html(handle, table, fields, rows, progress, total)
    if fmt == "xml":
        return _write_xml(handle, table, fields, rows, progress, total)
    if fmt == "sql":
        return _write_sql(handle, table, fields, rows, progress, total)
    raise ExportError(f"Unknown export format {fmt!r}.")


def _write_delimited(
    handle: Any,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    delimiter: str,
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
    writer.writerow([field.name for field in fields])
    count = 0
    for row in rows:
        writer.writerow([_text(row.values.get(field.name)) for field in fields])
        count += 1
        _report(progress, count, total)
    _report(progress, count, total, force=True)
    return count


def _write_json(
    handle: Any,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    handle.write("[\n")
    count = 0
    for row in rows:
        if count:
            handle.write(",\n")
        payload = {field.name: _json_cell(row.values.get(field.name)) for field in fields}
        handle.write("  " + json.dumps(payload, ensure_ascii=False))
        count += 1
        _report(progress, count, total)
    handle.write("\n]\n")
    _report(progress, count, total, force=True)
    return count


def _write_jsonl(
    handle: Any,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    count = 0
    for row in rows:
        payload = {field.name: _json_cell(row.values.get(field.name)) for field in fields}
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        count += 1
        _report(progress, count, total)
    _report(progress, count, total, force=True)
    return count


def _write_html(
    handle: Any,
    table: DatFile,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    title = html_escape(table.path.name)
    handle.write(
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:1rem}"
        "table{border-collapse:collapse;font-size:13px}"
        "th,td{border:1px solid #ccc;padding:4px 6px;text-align:left}"
        "th{background:#eee;position:sticky;top:0}</style>\n"
        "</head>\n<body>\n"
        f"<h1>{title}</h1>\n<table>\n<thead><tr>"
    )
    for field in fields:
        handle.write(f"<th>{html_escape(field.name)}</th>")
    handle.write("</tr></thead>\n<tbody>\n")
    count = 0
    for row in rows:
        handle.write("<tr>")
        for field in fields:
            handle.write(f"<td>{html_escape(_text(row.values.get(field.name)))}</td>")
        handle.write("</tr>\n")
        count += 1
        _report(progress, count, total)
    handle.write("</tbody>\n</table>\n</body>\n</html>\n")
    _report(progress, count, total, force=True)
    return count


def _write_xml(
    handle: Any,
    table: DatFile,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    table_name = xml_escape(_table_name(table))
    handle.write('<?xml version="1.0" encoding="utf-8"?>\n')
    handle.write(f'<table name="{table_name}">\n')
    count = 0
    for row in rows:
        handle.write("  <record>\n")
        for field in fields:
            name = xml_escape(field.name)
            value = xml_escape(_text(row.values.get(field.name)))
            handle.write(f'    <field name="{name}">{value}</field>\n')
        handle.write("  </record>\n")
        count += 1
        _report(progress, count, total)
    handle.write("</table>\n")
    _report(progress, count, total, force=True)
    return count


def _write_sql(
    handle: Any,
    table: DatFile,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    table_name = _quote_ident(_table_name(table))
    columns = ", ".join(_quote_ident(field.name) for field in fields)
    definitions = ", ".join(
        f"{_quote_ident(field.name)} {_sql_type(field)}" for field in fields
    )
    handle.write(f"CREATE TABLE {table_name} ({definitions});\n")
    count = 0
    batch: list[str] = []
    for row in rows:
        values = ", ".join(_sql_literal(row.values.get(field.name)) for field in fields)
        batch.append(f"({values})")
        count += 1
        if len(batch) >= 200:
            handle.write(f"INSERT INTO {table_name} ({columns}) VALUES\n")
            handle.write(",\n".join(batch) + ";\n")
            batch.clear()
        _report(progress, count, total)
    if batch:
        handle.write(f"INSERT INTO {table_name} ({columns}) VALUES\n")
        handle.write(",\n".join(batch) + ";\n")
    _report(progress, count, total, force=True)
    return count


def _write_xlsx(
    tmp: Path,
    table: DatFile,
    fields: Sequence[FieldDef],
    rows: Iterable[RecordRow],
    progress: ProgressCallback | None,
    total: int | None,
) -> int:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExportError(
            "Excel export needs openpyxl.",
            hint="Install it with: pip install openpyxl",
        ) from exc

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title=_sheet_title(_table_name(table)))
    sheet.append([field.name for field in fields])
    count = 0
    try:
        for row in rows:
            if count >= _EXCEL_MAX_ROWS - 1:
                raise ExportError(
                    f"Excel supports at most {_EXCEL_MAX_ROWS:,} rows including the header.",
                    hint="Use CSV, JSONL or SQL, which have no row cap.",
                )
            sheet.append([_xlsx_cell(row.values.get(field.name)) for field in fields])
            count += 1
            _report(progress, count, total)
    except BaseException:
        # Finish the streaming worksheet so openpyxl releases its temporary
        # file instead of complaining during garbage collection.
        with contextlib.suppress(Exception):
            sheet.close()
        raise
    workbook.save(tmp)
    _report(progress, count, total, force=True)
    return count


def _report(
    progress: ProgressCallback | None,
    done: int,
    total: int | None,
    force: bool = False,
) -> None:
    if progress is None:
        return
    if force or done == 1 or done % 1000 == 0:
        progress(done, total)


def _text(value: Any) -> str:
    return display_value(value)


def _json_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "as_tuple"):  # Decimal avoids float rounding in JSON
        return format(value, "f")
    return value


def _xlsx_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "as_tuple"):
        return float(value)
    return value


def _table_name(table: DatFile) -> str:
    name = table.header.record_name or table.path.stem
    return name or "DATA"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_type(field: FieldDef) -> str:
    if field.type_code == 1:
        return "INTEGER"
    if field.type_code == 2:
        return "DOUBLE PRECISION"
    if field.type_code in (3, 4):
        return f"VARCHAR({max(field.length, 1)})"
    if field.type_code in (5, 6):
        return "SMALLINT"
    if field.type_code == 8:
        return f"DECIMAL(31,{field.decimals})"
    return "BLOB"


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, bool):
        return "1" if value else "0"
    return format(value, "f") if hasattr(value, "as_tuple") else str(value)


def _sheet_title(name: str) -> str:
    cleaned = "".join(ch if ch not in '[]:*?/\\' else "_" for ch in name)
    return (cleaned or "DATA")[:31]
