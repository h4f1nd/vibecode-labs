from __future__ import annotations

import inspect
from pathlib import Path

from datbuilder import write_sample
from dotdat import __version__
from dotdat.ui.app import Api


def test_initial_state() -> None:
    api = Api()
    assert api.initial_state() == {"path": None, "encoding": "cp437", "version": __version__}


def test_load_and_page(sample_dat: Path) -> None:
    api = Api()
    try:
        result = api.load(str(sample_dat), "cp437")
        assert result["ok"] is True
        assert result["info"]["header"]["record_count"] == 4
        assert result["info"]["date_fields"] == []
        assert result["page"]["total"] == 3
        assert len(result["page"]["rows"]) == 3

        page = api.page(0, 2, False, None, None, False)
        assert page["ok"] is True
        assert page["page"]["total"] == 3
        assert page["page"]["has_more"] is True
        assert len(page["page"]["rows"]) == 2
    finally:
        api.close()


def test_page_filters_and_deleted(sample_dat: Path) -> None:
    api = Api()
    try:
        assert api.load(str(sample_dat))["ok"] is True
        page = api.page(0, 10, True, ["ID>=2"], "AMOUNT", True)
        assert page["ok"] is True
        assert [row["values"]["ID"] for row in page["page"]["rows"]] == [4, 3, 2]
        assert page["page"]["total"] == 3
    finally:
        api.close()


def test_bad_filter_returns_error(sample_dat: Path) -> None:
    api = Api()
    try:
        assert api.load(str(sample_dat))["ok"] is True
        result = api.page(0, 10, False, ["NOPE=1"], None, False)
        assert result["ok"] is False
        assert "Unknown field" in result["error"]
        assert result["hint"]
    finally:
        api.close()


def test_page_without_table() -> None:
    result = Api().page()
    assert result["ok"] is False
    assert "No file is open" in result["error"]


def test_load_missing_file(tmp_path: Path) -> None:
    result = Api().load(str(tmp_path / "nope.dat"))
    assert result["ok"] is False
    assert "error" in result


def test_load_corrupt_file(tmp_path: Path) -> None:
    bad = write_sample(tmp_path / "BROKEN.DAT", field_count=60_000)
    result = Api().load(str(bad))
    assert result["ok"] is False
    assert "60000 fields" in result["error"]


def test_export(sample_dat: Path, tmp_path: Path) -> None:
    api = Api()
    try:
        assert api.load(str(sample_dat))["ok"] is True
        out = tmp_path / "ui.csv"
        result = api.export("csv", str(out), False, ["ID>=2"], None, None, False)
        assert result["ok"] is True
        assert result["count"] == 2
        assert out.exists()
        assert "beta" in out.read_text(encoding="utf-8")
    finally:
        api.close()


def test_export_without_table(tmp_path: Path) -> None:
    result = Api().export("csv", str(tmp_path / "x.csv"))
    assert result["ok"] is False
    assert "No file is open" in result["error"]


def test_export_bad_format(sample_dat: Path, tmp_path: Path) -> None:
    api = Api()
    try:
        assert api.load(str(sample_dat))["ok"] is True
        result = api.export("nope", str(tmp_path / "x.bin"))
        assert result["ok"] is False
        assert "Unknown export format" in result["error"]
    finally:
        api.close()


def test_export_bad_fields(sample_dat: Path, tmp_path: Path) -> None:
    api = Api()
    try:
        assert api.load(str(sample_dat))["ok"] is True
        result = api.export("csv", str(tmp_path / "x.csv"), False, None, ["NOPE"])
        assert result["ok"] is False
        assert "Unknown field" in result["error"]
    finally:
        api.close()


def test_close(sample_dat: Path) -> None:
    api = Api()
    assert api.load(str(sample_dat))["ok"] is True
    assert api.close() is True
    assert api.page()["ok"] is False


def test_cancel_is_lock_free() -> None:
    api = Api()
    assert api.cancel() is True


def test_bridge_signatures_are_positional() -> None:
    assert list(inspect.signature(Api.load).parameters) == ["self", "path", "encoding"]
    assert list(inspect.signature(Api.page).parameters) == [
        "self",
        "offset",
        "limit",
        "include_deleted",
        "filters",
        "sort",
        "desc",
    ]
    assert list(inspect.signature(Api.export).parameters) == [
        "self",
        "fmt",
        "path",
        "include_deleted",
        "filters",
        "fields",
        "sort",
        "desc",
    ]
    assert list(inspect.signature(Api.export_dialog).parameters) == ["self", "suggested"]
