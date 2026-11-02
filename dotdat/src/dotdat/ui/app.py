"""pywebview shell and JavaScript bridge.

Every bridge method is positionally callable: pywebview passes arguments in
order and the GUI calls them that way. Keep the signatures stable.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .. import __version__
from ..datfile import DatFile
from ..errors import DotDatError
from ..exporter import export_table
from ..query import compile_filters

WEB_DIR = Path(__file__).with_name("web")
DAT_FILTER = "Clarion DAT (*.dat;*.DAT)"


class Api:
    """Stateful bridge. One open table at a time."""

    def __init__(self) -> None:
        self._table: DatFile | None = None
        self._lock = threading.RLock()
        self._cancel = False
        self._initial_path: str | None = None
        self._initial_encoding = "cp437"

    # ------------------------------------------------------------- lifecycle

    def initial_state(self) -> dict[str, Any]:
        return {
            "path": self._initial_path,
            "encoding": self._initial_encoding,
            "version": __version__,
        }

    def load(self, path: str, encoding: str = "cp437") -> dict[str, Any]:
        try:
            with self._lock:
                previous = self._table
                self._table = None
                if previous is not None:
                    previous.close()
                table = DatFile(Path(path), encoding=encoding)
                self._table = table
                page = table.page(offset=0, limit=100)
                return {
                    "ok": True,
                    "info": table.info_dict(),
                    "page": page.to_dict(),
                }
        except DotDatError as exc:
            return _error(exc)
        except OSError as exc:
            return {
                "ok": False,
                "error": f"Cannot open {path}: {exc.strerror or exc}",
                "hint": "Check that the file exists and is readable.",
            }

    def close(self) -> bool:
        with self._lock:
            if self._table is not None:
                self._table.close()
                self._table = None
        return True

    # ---------------------------------------------------------------- reading

    def page(
        self,
        offset: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
        filters: list[str] | None = None,
        sort: str | None = None,
        desc: bool = False,
    ) -> dict[str, Any]:
        try:
            with self._lock:
                table = self._require()
                predicate = compile_filters(filters or [], table.fields)
                page = table.page(
                    int(offset),
                    int(limit),
                    bool(include_deleted),
                    predicate,
                    sort or None,
                    bool(desc),
                )
                return {"ok": True, "page": page.to_dict()}
        except DotDatError as exc:
            return _error(exc)

    # --------------------------------------------------------------- exporting

    def export(
        self,
        fmt: str,
        path: str,
        include_deleted: bool = False,
        filters: list[str] | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        desc: bool = False,
    ) -> dict[str, Any]:
        self._cancel = False
        try:
            with self._lock:
                table = self._require()
                predicate = compile_filters(filters or [], table.fields)
                count = export_table(
                    table,
                    Path(path),
                    fmt,
                    include_deleted=bool(include_deleted),
                    predicate=predicate,
                    fields=fields or None,
                    sort=sort or None,
                    desc=bool(desc),
                    force=True,
                    cancel=lambda: self._cancel,
                )
                return {"ok": True, "count": count, "path": path}
        except DotDatError as exc:
            return _error(exc)
        except OSError as exc:
            return {
                "ok": False,
                "error": f"Cannot write {path}: {exc.strerror or exc}",
                "hint": "Choose another folder or close the file in Excel.",
            }

    def cancel(self) -> bool:
        # Deliberately lock-free: an export holds the lock while it runs.
        self._cancel = True
        return True

    # ---------------------------------------------------------------- dialogs

    def pick_file(self) -> str | None:
        import webview

        if not webview.windows:
            return None
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=(DAT_FILTER, "All files (*.*)"),
        )
        return _first_path(result)

    def export_dialog(self, suggested: str = "") -> str | None:
        import webview

        if not webview.windows:
            return None
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested or "export.dat",
            file_types=("All files (*.*)",),
        )
        return _first_path(result)

    # ----------------------------------------------------------------- helpers

    def _require(self) -> DatFile:
        if self._table is None:
            raise DotDatError(
                "No file is open.",
                hint="Use Open to choose a Clarion .DAT file.",
            )
        return self._table


def _first_path(result: Any) -> str | None:
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return str(result[0]) if result else None
    return str(result)


def _error(exc: DotDatError) -> dict[str, Any]:
    return {"ok": False, "error": exc.message, "hint": exc.hint}


def run_gui(path: Path | None = None, encoding: str = "cp437") -> None:
    """Open the desktop window and block until it closes."""
    import webview

    api = Api()
    if path is not None:
        api._initial_path = str(Path(path))
    api._initial_encoding = encoding
    webview.create_window(
        "DOTDAT",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1280,
        height=840,
        min_size=(900, 600),
    )
    webview.start()
