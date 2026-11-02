from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dotdat import __version__
from dotdat.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_formats() -> None:
    result = runner.invoke(app, ["formats"])
    assert result.exit_code == 0
    for fmt in ("csv", "jsonl", "xlsx"):
        assert fmt in result.output


def test_info(sample_dat: Path) -> None:
    result = runner.invoke(app, ["info", str(sample_dat)])
    assert result.exit_code == 0
    assert "SAMPLE.DAT" in result.output
    assert "Structure" in result.output
    assert "ID_KEY" in result.output


def test_info_json(sample_dat: Path) -> None:
    result = runner.invoke(app, ["info", str(sample_dat), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["header"]["record_count"] == 4
    assert payload["fields"][0]["name"] == "ID"


def test_rows(sample_dat: Path) -> None:
    result = runner.invoke(app, ["rows", str(sample_dat), "-n", "2"])
    assert result.exit_code == 0
    assert "ALPHA" in result.output
    assert "Gamma" not in result.output


def test_rows_json(sample_dat: Path) -> None:
    result = runner.invoke(app, ["rows", str(sample_dat), "-n", "2", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total"] == 3
    assert [row["record"] for row in payload["rows"]] == [1, 2]


def test_rows_fields_and_filter(sample_dat: Path) -> None:
    result = runner.invoke(
        app,
        [
            "rows",
            str(sample_dat),
            "-n",
            "10",
            "--fields",
            "ID,NAME",
            "--where",
            "ID>=2",
        ],
    )
    assert result.exit_code == 0
    assert "beta" in result.output
    assert "AMOUNT" not in result.output


def test_rows_include_deleted(sample_dat: Path) -> None:
    result = runner.invoke(app, ["rows", str(sample_dat), "-n", "10", "--include-deleted"])
    assert result.exit_code == 0
    assert "DELETED" in result.output
    assert "hidden" not in result.output


def test_rows_bad_filter(sample_dat: Path) -> None:
    result = runner.invoke(app, ["rows", str(sample_dat), "-w", "NOPE=1"])
    assert result.exit_code == 2
    assert "Unknown field" in result.output


def test_export_csv(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    result = runner.invoke(app, ["export", str(sample_dat), "-f", "csv", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "exported 3 rows" in result.output


def test_export_default_name(sample_dat: Path) -> None:
    result = runner.invoke(app, ["export", str(sample_dat), "-f", "jsonl"])
    default = sample_dat.with_suffix(".jsonl")
    assert result.exit_code == 0
    assert default.exists()
    assert default.read_text(encoding="utf-8").count("\n") == 3
    default.unlink()


def test_export_needs_force(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    out.write_text("old", encoding="utf-8")
    result = runner.invoke(app, ["export", str(sample_dat), "-o", str(out)])
    assert result.exit_code == 2
    assert "already exists" in result.output
    result = runner.invoke(app, ["export", str(sample_dat), "-o", str(out), "--force"])
    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8").startswith("ID,")


def test_export_quiet(sample_dat: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    result = runner.invoke(app, ["export", str(sample_dat), "-o", str(out), "-q"])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_export_unknown_format(sample_dat: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", str(sample_dat), "-f", "nope"])
    assert result.exit_code == 2
    assert "Unknown format" in result.output


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "dotdat" in result.output
    assert "python" in result.output
    assert "openpyxl" in result.output


def test_missing_file() -> None:
    result = runner.invoke(app, ["info", "does-not-exist.dat"])
    assert result.exit_code != 0


def test_kod_style_corrupt_file(tmp_path: Path) -> None:
    from datbuilder import write_sample

    bad = write_sample(tmp_path / "BROKEN.DAT", field_count=60_000)
    result = runner.invoke(app, ["info", str(bad)])
    assert result.exit_code == 2
    assert "60000 fields" in result.output
    assert "Traceback" not in result.output


def test_not_a_dat(tmp_path: Path) -> None:
    bad = tmp_path / "plain.dat"
    bad.write_bytes(b"hello" * 20)
    result = runner.invoke(app, ["info", str(bad)])
    assert result.exit_code == 2
    assert "not a Clarion 2.x DAT" in result.output


def test_unknown_encoding(sample_dat: Path) -> None:
    result = runner.invoke(app, ["info", str(sample_dat), "-e", "not-a-codec"])
    assert result.exit_code == 2
    assert "Unknown text encoding" in result.output
    assert "Traceback" not in result.output


def test_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "info" in result.output
    assert "export" in result.output
