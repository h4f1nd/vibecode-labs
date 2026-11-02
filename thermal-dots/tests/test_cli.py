from __future__ import annotations

import json
import re
import shutil

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from thermaldots.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "thermal-dots" in result.output


def test_convert_writes_png_and_sidecar(gradient_png, tmp_path) -> None:
    target = tmp_path / "out.png"
    result = runner.invoke(app, ["convert", str(gradient_png), "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.exists()
    sidecar = target.with_suffix(".png.json")
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["width"] == 384
    assert payload["options"]["dither"] == "bayer4"


def test_convert_80mm_and_escpos(gradient_png, tmp_path) -> None:
    target = tmp_path / "out.bin"
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "-o",
            str(target),
            "--paper",
            "80",
            "--dither",
            "halftone",
            "--format",
            "bin",
            "--no-sidecar",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = target.read_bytes()
    assert payload[:2] == b"\x1b@"
    assert payload[2:6] == b"\x1dv0\x00"
    assert payload[6:8] == (72).to_bytes(2, "little")


def test_convert_default_output_name(gradient_png, tmp_path) -> None:
    source = tmp_path / "photo.png"
    shutil.copy(gradient_png, source)
    result = runner.invoke(app, ["convert", str(source)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "photo_58mm_bayer4.png").exists()


def test_convert_json_output(gradient_png, tmp_path) -> None:
    result = runner.invoke(
        app,
        ["convert", str(gradient_png), "-o", str(tmp_path / "o.png"), "--json"],
    )
    assert result.exit_code == 0, result.output
    assert '"width": 384' in result.output


def test_invalid_dither_exits_with_error(gradient_png, tmp_path) -> None:
    result = runner.invoke(
        app, ["convert", str(gradient_png), "-o", str(tmp_path / "x.png"), "--dither", "nope"]
    )
    assert result.exit_code == 2
    assert "Unknown dither mode" in result.output


def test_missing_file_exits_with_error(tmp_path) -> None:
    result = runner.invoke(app, ["convert", str(tmp_path / "nope.png")])
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_batch_continues_after_bad_file(gradient_png, corrupt_file, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "good.png")
    shutil.copy(corrupt_file, inbox / "bad.jpg")

    result = runner.invoke(app, ["batch", str(inbox), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert (tmp_path / "out" / "good_58mm.png").exists()
    assert "bad.jpg" in result.output


def test_batch_empty_folder(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["batch", str(empty), "-o", str(tmp_path / "out")])
    assert result.exit_code == 2


def test_batch_custom_width(gradient_png, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "p.png")
    out = tmp_path / "out"

    result = runner.invoke(
        app, ["batch", str(inbox), "-o", str(out), "-p", "custom", "-w", "512"]
    )

    assert result.exit_code == 0, result.output
    assert out.joinpath("p_custom.png").exists()


def test_batch_custom_paper_without_width_explains(gradient_png, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "p.png")
    result = runner.invoke(app, ["batch", str(inbox), "-o", str(tmp_path / "out"), "-p", "custom"])
    assert result.exit_code == 2
    assert "requires width_dots" in result.output


def test_preview_prints_blocks(gradient_png) -> None:
    result = runner.invoke(app, ["preview", str(gradient_png), "-c", "20"])
    assert result.exit_code == 0, result.output
    assert "\u2588" in result.output or "\u2580" in result.output


@pytest.mark.parametrize(
    "flags",
    [
        ["-p", "80"],
        ["-p", "custom", "-w", "512"],
        ["-d", "halftone"],
        ["-d", "mean", "--threshold", "160"],
        ["--gamma", "0.7"],
        ["--contrast", "1.4", "--brightness", "-20"],
        ["--scale", "fill", "--max-height", "200"],
        ["--rotate", "90"],
        ["--margin", "8", "--border"],
        ["--invert"],
    ],
)
def test_preview_accepts_every_convert_option(gradient_png, flags: list[str]) -> None:
    """A preview that cannot express the real export is a trap."""
    result = runner.invoke(app, ["preview", str(gradient_png), "-c", "20", *flags])
    assert result.exit_code == 0, result.output
    assert "dots" in result.output


def test_preview_gamma_changes_ink(gradient_png) -> None:
    def ink(*flags: str) -> float:
        out = runner.invoke(app, ["preview", str(gradient_png), "-c", "20", *flags]).output
        match = re.search(r"ink ([0-9.]+)%", out)
        assert match, out
        return float(match.group(1))

    assert ink("--gamma", "0.6") < ink() < ink("--gamma", "1.6")


def test_preset_applies_paper_and_dither(gradient_png, tmp_path) -> None:
    out = tmp_path / "wide.png"
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--preset", "wide-hacker", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert Image.open(out).size[0] == 576

    out2 = tmp_path / "news.png"
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--preset", "newsprint", "-o", str(out2)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "news.png.json").read_text(encoding="utf-8"))
    assert metadata["options"]["dither"] == "halftone"
    assert metadata["options"]["gamma"] == 1.2


def test_explicit_flag_overrides_preset(gradient_png) -> None:
    def ink(*flags: str) -> float:
        out = runner.invoke(app, ["preview", str(gradient_png), "-c", "20", *flags]).output
        match = re.search(r"ink ([0-9.]+)%", out)
        assert match, out
        return float(match.group(1))

    preset_only = ink("--preset", "newsprint")
    overridden = ink("--preset", "newsprint", "--gamma", "0.6")
    assert overridden < preset_only


def test_unknown_preset_lists_the_valid_ones(gradient_png, tmp_path) -> None:
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--preset", "nope", "-o", str(tmp_path / "x.png")]
    )
    assert result.exit_code == 2
    assert "Unknown preset" in result.output
    assert "newsprint" in result.output


def test_every_advertised_preset_converts(gradient_png) -> None:
    """`tdots presets` must not advertise a preset the CLI cannot apply."""
    from thermaldots.profiles import PRESETS

    for name in PRESETS:
        result = runner.invoke(app, ["preview", str(gradient_png), "-c", "10", "--preset", name])
        assert result.exit_code == 0, (name, result.output)


def test_batch_accepts_tone_options(gradient_png, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "p.png")
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["batch", str(inbox), "-o", str(out), "--gamma", "0.8", "--contrast", "1.2", "--border"],
    )
    assert result.exit_code == 0, result.output
    assert out.joinpath("p_58mm.png").exists()


def test_info(gradient_png) -> None:
    result = runner.invoke(app, ["info", str(gradient_png)])
    assert result.exit_code == 0
    assert "640" in result.output


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "58 mm" in result.output


def test_presets() -> None:
    result = runner.invoke(app, ["presets"])
    assert result.exit_code == 0
    assert "hacker-bayer" in result.output

def test_invalid_compress_level_is_a_clean_error(gradient_png, tmp_path) -> None:
    result = runner.invoke(
        app,
        ["convert", str(gradient_png), "--compress-level", "12", "-o", str(tmp_path / "x.png")],
    )
    assert result.exit_code == 2
    assert "compress-level" in result.output
    assert "Traceback" not in result.output


def test_preview_rejects_zero_columns(gradient_png) -> None:
    result = runner.invoke(app, ["preview", str(gradient_png), "-c", "0"])
    assert result.exit_code == 2
    assert "columns" in result.output
    assert "Traceback" not in result.output

def test_double_click_detection(monkeypatch) -> None:
    import thermaldots.cli as cli

    monkeypatch.setattr(cli, "_is_frozen", lambda: True)
    monkeypatch.setattr(cli, "_has_console", lambda: False)
    monkeypatch.setattr(cli.sys, "argv", ["C:\\x\\tdots.exe"])
    assert cli._double_clicked() is True

    monkeypatch.setattr(cli, "_has_console", lambda: True)
    assert cli._double_clicked() is False

    monkeypatch.setattr(cli, "_has_console", lambda: False)
    monkeypatch.setattr(cli.sys, "argv", ["C:\\x\\tdots.exe", "convert"])
    assert cli._double_clicked() is False

    monkeypatch.setattr(cli.sys, "argv", ["C:\\x\\tdots.exe"])
    monkeypatch.setattr(cli, "_is_frozen", lambda: False)
    assert cli._double_clicked() is False


def test_double_click_opens_gui(monkeypatch) -> None:
    """A frozen exe launched from Explorer must show the GUI, not print help."""
    import thermaldots.cli as cli
    import thermaldots.ui.app as ui

    calls: list[dict] = []
    monkeypatch.setattr(ui, "main", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(cli, "_double_clicked", lambda: True)
    monkeypatch.setattr(cli, "app", lambda: pytest.fail("the CLI must not run"))

    cli.main()
    assert calls == [{}]


def test_upscale_enlarges_png_and_sidecar(gradient_png, tmp_path) -> None:
    target = tmp_path / "big.png"
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--upscale", "2", "-o", str(target)]
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size == (768, 576)

    payload = json.loads(target.with_suffix(".png.json").read_text(encoding="utf-8"))
    assert payload["upscale"] == 2
    assert payload["pixel_width"] == 768
    assert payload["pixel_height"] == 576


def test_upscale_auto_matches_source_width(gradient_png, tmp_path) -> None:
    """640 px source / 384 dots -> factor 2."""
    target = tmp_path / "auto.png"
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--upscale", "auto", "-o", str(target)]
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size == (768, 576)

    payload = json.loads(target.with_suffix(".png.json").read_text(encoding="utf-8"))
    assert payload["upscale"] == 2


def test_upscale_applies_to_batch(gradient_png, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "p.png")
    out = tmp_path / "out"
    result = runner.invoke(app, ["batch", str(inbox), "-o", str(out), "--upscale", "2"])
    assert result.exit_code == 0, result.output
    with Image.open(out / "p_58mm_x2.png") as image:
        assert image.size == (768, 576)


@pytest.mark.parametrize("value", ["0", "17", "nope"])
def test_upscale_out_of_range_is_a_clean_error(gradient_png, tmp_path, value) -> None:
    result = runner.invoke(
        app,
        ["convert", str(gradient_png), "--upscale", value, "-o", str(tmp_path / "x.png")],
    )
    assert result.exit_code == 2
    assert "upscale" in result.output
    assert "Traceback" not in result.output


def test_upscale_is_rejected_for_printer_bytes(gradient_png, tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "-f",
            "bin",
            "--upscale",
            "2",
            "-o",
            str(tmp_path / "x.bin"),
        ],
    )
    assert result.exit_code == 2
    assert "upscale only applies" in result.output


def test_render_native_matches_source_width(gradient_png, tmp_path) -> None:
    target = tmp_path / "header.png"
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "--preset",
            "header",
            "--render-width",
            "native",
            "-o",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size == (640, 480)
        assert image.mode == "1"

    payload = json.loads(target.with_suffix(".png.json").read_text(encoding="utf-8"))
    assert payload["width"] == 640
    assert payload["screen_export"] is True
    assert payload["options"]["dither"] == "mean"
    assert payload["options"]["render_width"] == 640


def test_render_explicit_width(gradient_png, tmp_path) -> None:
    target = tmp_path / "wide.png"
    result = runner.invoke(
        app,
        ["convert", str(gradient_png), "--render-width", "1920", "-o", str(target)],
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size == (1920, 1440)


def test_render_default_name_uses_the_pixel_width(gradient_png, tmp_path) -> None:
    source = tmp_path / "logo.png"
    shutil.copy(gradient_png, source)
    result = runner.invoke(app, ["convert", str(source), "--render-width", "native"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "logo_640px_bayer4.png").exists()


def test_render_native_with_upscale_auto_stays_at_source_size(
    gradient_png, tmp_path
) -> None:
    target = tmp_path / "auto.png"
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "--render-width",
            "native",
            "--upscale",
            "auto",
            "-o",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size == (640, 480)


def test_render_applies_to_batch_per_file(gradient_png, tmp_path) -> None:
    inbox = tmp_path / "in"
    inbox.mkdir()
    shutil.copy(gradient_png, inbox / "wide.png")
    Image.new("RGB", (320, 240), (255, 255, 255)).save(inbox / "small.png")

    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["batch", str(inbox), "-o", str(out), "--render-width", "native"],
    )
    assert result.exit_code == 0, result.output
    assert Image.open(out / "wide_640px.png").size == (640, 480)
    assert Image.open(out / "small_320px.png").size == (320, 240)


@pytest.mark.parametrize("value", ["4", "8193", "nope"])
def test_render_width_out_of_range_is_a_clean_error(
    gradient_png, tmp_path, value
) -> None:
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "--render-width",
            value,
            "-o",
            str(tmp_path / "x.png"),
        ],
    )
    assert result.exit_code == 2
    assert "render-width" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("fmt", ["bin", "txt"])
def test_render_is_rejected_for_printer_and_text(gradient_png, tmp_path, fmt) -> None:
    result = runner.invoke(
        app,
        [
            "convert",
            str(gradient_png),
            "-f",
            fmt,
            "--render-width",
            "native",
            "-o",
            str(tmp_path / f"x.{fmt}"),
        ],
    )
    assert result.exit_code == 2
    assert "render-width only applies" in result.output


def test_preset_header_still_prints_when_no_render_width_is_given(
    gradient_png, tmp_path
) -> None:
    target = tmp_path / "printable.png"
    result = runner.invoke(
        app, ["convert", str(gradient_png), "--preset", "header", "-o", str(target)]
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as image:
        assert image.size[0] == 576

def test_header_native_keeps_solid_black_and_white(tmp_path) -> None:
    """No dither texture: a solid logo stays solid at native resolution."""
    source = tmp_path / "logo.png"
    image = Image.new("RGB", (800, 200), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((50, 50, 300, 150), fill=(0, 0, 0))
    image.save(source)

    target = tmp_path / "header.png"
    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            "--preset",
            "header",
            "--render-width",
            "native",
            "-o",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    with Image.open(target) as output:
        assert output.mode == "1"
        assert output.size == (800, 200)
        pixels = output.load()
        assert pixels[10, 10] == 255
        assert all(pixels[x, 100] == 0 for x in range(60, 290))
