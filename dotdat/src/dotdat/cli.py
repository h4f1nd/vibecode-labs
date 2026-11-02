"""dotdat command line interface."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import __version__
from .codec import display_value, format_clarion_timestamp
from .datfile import DatFile
from .errors import DotDatError
from .exporter import EXPORT_FORMATS, EXTENSIONS, export_table, select_fields
from .models import FieldDef, Page, RecordRow
from .query import compile_filters

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)


@app.callback()
def _root(ctx: typer.Context) -> None:
    """Read-only viewer and exporter for Clarion 2.x DAT tables."""
    if ctx.invoked_subcommand is not None:
        return
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        _launch_gui(None, "cp437")
        return
    typer.echo(ctx.get_help())


@app.command()
def info(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    encoding: str = typer.Option("cp437", "--encoding", "-e", help="Text encoding."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show the header, fields and keys of a DAT file."""
    try:
        with _open(path, encoding) as table:
            if as_json:
                typer.echo(json.dumps(table.info_dict(), indent=2, ensure_ascii=False))
                return
            _print_info(table)
    except DotDatError as exc:
        _die(exc)


@app.command()
def rows(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=10_000),
    offset: int = typer.Option(0, "--offset", min=0),
    where: list[str] | None = typer.Option(None, "--where", "-w", help="FIELD=VALUE filter."),
    fields: str | None = typer.Option(None, "--fields", help="Comma-separated columns."),
    include_deleted: bool = typer.Option(False, "--include-deleted"),
    sort: str | None = typer.Option(None, "--sort", help="Field name to sort by."),
    desc: bool = typer.Option(False, "--desc", help="Sort descending."),
    encoding: str = typer.Option("cp437", "--encoding", "-e"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a page of records."""
    try:
        with _open(path, encoding) as table:
            predicate = compile_filters(where or [], table.fields)
            page = table.page(
                offset=offset,
                limit=limit,
                include_deleted=include_deleted,
                predicate=predicate,
                sort=sort,
                desc=desc,
            )
            if as_json:
                typer.echo(json.dumps(page.to_dict(), indent=2, ensure_ascii=False))
                return
            selected = select_fields(table, _split(fields))
            _print_rows(table, page, selected, include_deleted)
    except DotDatError as exc:
        _die(exc)


@app.command()
def export(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    fmt: str = typer.Option("csv", "--format", "-f", help=f"One of: {', '.join(EXPORT_FORMATS)}"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    where: list[str] | None = typer.Option(None, "--where", "-w"),
    fields: str | None = typer.Option(None, "--fields", help="Comma-separated columns."),
    include_deleted: bool = typer.Option(False, "--include-deleted"),
    sort: str | None = typer.Option(None, "--sort"),
    desc: bool = typer.Option(False, "--desc"),
    encoding: str = typer.Option("cp437", "--encoding", "-e"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Export records to CSV, TXT, JSON, HTML, XML, SQL or XLSX."""
    try:
        fmt = fmt.casefold()
        if fmt not in EXPORT_FORMATS:
            raise DotDatError(
                f"Unknown format {fmt!r}.",
                hint=f"Choose one of: {', '.join(EXPORT_FORMATS)}.",
            )
        destination = output or path.with_suffix(EXTENSIONS[fmt])
        with _open(path, encoding) as table:
            predicate = compile_filters(where or [], table.fields)
            count = _run_export(
                table,
                destination,
                fmt,
                predicate=predicate,
                fields=_split(fields),
                include_deleted=include_deleted,
                sort=sort,
                desc=desc,
                force=force,
                quiet=quiet,
            )
        if not quiet:
            console.print(
                f"[green]exported[/] {count:,} rows to [bold]{destination}[/]",
            )
    except DotDatError as exc:
        _die(exc)


@app.command("formats")
def formats_command() -> None:
    """List supported export formats."""
    table = Table(title="Export formats", box=box.SIMPLE)
    table.add_column("format")
    table.add_column("extension")
    for name in EXPORT_FORMATS:
        table.add_row(name, EXTENSIONS[name])
    console.print(table)


@app.command()
def gui(
    path: Path | None = typer.Argument(None, exists=True, dir_okay=False, readable=True),
    encoding: str = typer.Option("cp437", "--encoding", "-e"),
) -> None:
    """Open the desktop viewer."""
    _launch_gui(path, encoding)


@app.command()
def doctor() -> None:
    """Check the runtime pieces DOTDAT needs."""
    console.print(f"dotdat          [green]{__version__}[/]")
    console.print(f"python          {sys.version.split()[0]}")
    console.print(f"executable      {sys.executable}")
    for label, module in (("openpyxl", "openpyxl"), ("pywebview", "webview")):
        try:
            __import__(module)
        except ImportError:
            console.print(f"{label:<15} [red]missing[/]")
        else:
            console.print(f"{label:<15} [green]ok[/]")
    if sys.platform == "win32":
        runtime = _webview2_version()
        if runtime:
            console.print(f"webview2        [green]{runtime}[/]")
        else:
            console.print("webview2        [red]not found[/]")
    try:
        import tkinter  # noqa: F401

        console.print("tkinter         [green]ok[/]")
    except ImportError:
        console.print("tkinter         [yellow]missing[/]")


def _webview2_version() -> str | None:
    """Version of the installed Edge WebView2 runtime, when detectable."""
    if sys.platform != "win32":
        return None
    import winreg

    product = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    candidates = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{product}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{product}",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            rf"Software\Microsoft\EdgeUpdate\Clients\{product}",
        ),
    )
    for root, subkey in candidates:
        try:
            with winreg.OpenKey(root, subkey) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version:
            return str(version)
    return None


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


def _open(path: Path, encoding: str) -> DatFile:
    try:
        return DatFile(path, encoding=encoding)
    except OSError as exc:
        raise DotDatError(
            f"Cannot open {path}: {exc.strerror or exc}",
            hint="Check that the file exists and is readable.",
        ) from exc


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts or None


def _print_info(table: DatFile) -> None:
    header = table.header
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="bold cyan", justify="right")
    meta.add_column()
    rows: tuple[tuple[str, str], ...] = (
        ("file", str(table.path)),
        ("size", f"{table.size:,} bytes"),
        ("signature", header.signature_hex),
        ("attributes", f"{header.attributes} ({header.attributes:#06x})"),
        ("records", f"{header.record_count:,}"),
        ("deleted", f"{header.deleted_count:,}"),
        ("active", f"{header.active_count:,}"),
        ("fields", f"{header.field_count}"),
        ("keys", f"{header.key_count}"),
        ("record length", f"{header.record_length} bytes ({header.payload_size} payload)"),
        ("data offset", f"{header.data_offset:,}"),
        ("record name", header.record_name or "(none)"),
        ("file prefix", header.file_prefix or "(none)"),
        ("record prefix", header.record_prefix or "(none)"),
        (
            "last change",
            format_clarion_timestamp(header.last_change_date, header.last_change_time),
        ),
        ("encoding", table.encoding),
    )
    for label, value in rows:
        meta.add_row(label, value)
    console.print(Panel(meta, title=f"Dotdat / {table.path.name}", border_style="green"))

    fields = Table(title="Structure", box=box.SIMPLE_HEAVY)
    fields.add_column("#", justify="right", style="dim")
    fields.add_column("name", style="bold")
    fields.add_column("type")
    fields.add_column("offset", justify="right")
    fields.add_column("length", justify="right")
    fields.add_column("format", justify="right")
    fields.add_column("dec", justify="right")
    fields.add_column("array", justify="right")
    for field in table.fields:
        fields.add_row(
            str(field.index),
            field.name,
            field.type_name,
            str(field.offset),
            str(field.length),
            f"{field.significant}.{field.decimals}" if field.significant else "",
            str(field.decimals),
            str(field.array_number or ""),
        )
    console.print(fields)

    if table.keys:
        keys = Table(title="Keys", box=box.SIMPLE_HEAVY)
        keys.add_column("#", justify="right", style="dim")
        keys.add_column("name", style="bold")
        keys.add_column("parts", justify="right")
        keys.add_column("type", justify="right")
        keys.add_column("fields")
        by_number = {field.index: field for field in table.fields}
        for key in table.keys:
            components = ", ".join(
                f"{by_number[part.field_number].name} ({by_number[part.field_number].type_name})"
                if part.field_number in by_number
                else f"field {part.field_number}"
                for part in key.parts
            )
            keys.add_row(
                str(key.index),
                key.name,
                str(key.components),
                f"0x{key.composite_type:04X}",
                components,
            )
        console.print(keys)


def _print_rows(
    table: DatFile,
    page: Page,
    selected: list[FieldDef],
    include_deleted: bool,
) -> None:
    grid = Table(box=box.SIMPLE, show_lines=False)
    grid.add_column("rec", justify="right", style="dim")
    for field in selected:
        grid.add_column(field.name)
    for row in page.rows:
        values = [row.values.get(field.name, "") for field in selected]
        grid.add_row(str(row.number), *(_cell(value) for value in values))
    console.print(grid)
    if len(selected) > 8:
        console.print(
            "[dim]Columns may be cropped in a narrow terminal; "
            "pass --fields to choose fewer.[/]"
        )
    total = f"{page.total:,}" if page.total is not None else "unknown"
    console.print(
        f"[dim]{len(page.rows)} row(s) shown, starting at {page.offset:,}, "
        f"total {total}.[/]"
    )
    if table.header.deleted_count and not include_deleted:
        console.print(
            f"[dim]{table.header.deleted_count:,} deleted row(s) are hidden; "
            "pass --include-deleted to show them.[/]"
        )


def _cell(value: object) -> str:
    return display_value(value)


def _run_export(
    table: DatFile,
    destination: Path,
    fmt: str,
    *,
    predicate: Callable[[RecordRow], bool] | None,
    fields: list[str] | None,
    include_deleted: bool,
    sort: str | None,
    desc: bool,
    force: bool,
    quiet: bool,
) -> int:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=quiet,
    ) as progress:
        task = progress.add_task("exporting", total=None)

        def on_progress(done: int, total: int | None) -> None:
            if total is None:
                progress.update(task, description=f"exporting {done:,} rows")
            else:
                progress.update(task, total=total, completed=done)

        return export_table(
            table,
            destination,
            fmt,
            include_deleted=include_deleted,
            predicate=predicate,
            fields=fields,
            sort=sort,
            desc=desc,
            force=force,
            progress=on_progress,
        )


def _launch_gui(path: Path | None, encoding: str) -> None:
    try:
        from .ui.app import run_gui
    except ImportError as exc:
        _die(
            DotDatError(
                "The GUI needs pywebview.",
                hint='Install it with: pip install "dotdat[gui]"',
            )
        )
        raise exc
    try:
        run_gui(path, encoding)
    except DotDatError as exc:
        _die(exc)


def _die(exc: DotDatError) -> NoReturn:
    error_console.print(f"[red]error[/] {exc.message}")
    if exc.hint:
        error_console.print(f"[yellow]hint[/]  {exc.hint}")
    raise typer.Exit(code=2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
