"""Contract tests for the pywebview bridge.

The JS side calls these methods, so their *names, order and positional-ness*
are user-visible API.  pywebview passes positional arguments only, which makes
accidental keyword-only parameters a silent breakage - hence the signature test.
"""

from __future__ import annotations

import base64
import inspect
import io
import json

import pytest
from PIL import Image, ImageDraw

from thermaldots.ui.app import Api

WIDTH, HEIGHT = 160, 120


def _png_bytes() -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((0, 0, WIDTH // 2, HEIGHT // 2), fill=(0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode("ascii")


def _default_options() -> dict[str, object]:
    """Mirror of ``readOptions()`` in web/app.js."""
    return {
        "paper": "58mm",
        "width_dots": None,
        "dither": "bayer4",
        "threshold": 128,
        "auto_threshold": True,
        "gamma": 1.2,
        "brightness": 0,
        "contrast": 1.1,
        "invert": False,
        "scale": "fit",
        "rotate": 0,
        "margin": 0,
        "border": False,
        "max_height_dots": None,
        "max_source_pixels": 120_000_000,
        "render_width": None,
    }


@pytest.fixture()
def api() -> Api:
    return Api()


@pytest.fixture()
def handle(api: Api) -> str:
    loaded = api.load_image(_data_url(), "sample.png")
    assert loaded["ok"] is True
    return str(loaded["handle"])


def test_bootstrap_shape(api: Api) -> None:
    boot = api.bootstrap()
    assert boot["ok"] is True
    assert set(boot["formats"]) == {"png", "bmp", "bin", "txt"}
    assert "bayer4" in boot["dithers"]
    assert "hacker-bayer" in boot["presets"]
    assert {entry["paper"] for entry in boot["papers"]} == {"58mm", "80mm"}


def test_load_image_returns_handle_and_source(api: Api) -> None:
    loaded = api.load_image(_data_url(), "sample.png")
    assert loaded["ok"] is True
    assert loaded["name"] == "sample.png"
    assert loaded["source"]["width"] == WIDTH
    assert loaded["source"]["format"] == "PNG"
    assert loaded["handle"]


def test_load_image_rejects_garbage(api: Api) -> None:
    result = api.load_image("data:image/png;base64,bm90IGFuIGltYWdl", "bad.png")
    assert result["ok"] is False
    assert result["message"]
    assert result["hint"]


def test_load_image_rejects_non_data_url(api: Api) -> None:
    result = api.load_image("https://example.com/a.png", "a.png")
    assert result["ok"] is False


def test_preview_matches_engine_contract(api: Api, handle: str) -> None:
    payload = api.preview(handle, _default_options())
    assert payload["ok"] is True
    assert payload["image"].startswith("data:image/png;base64,")
    assert payload["width"] == 384
    assert payload["row_bytes"] == 48
    assert payload["raster_bytes"] == payload["row_bytes"] * payload["height"]
    assert 0.0 <= payload["ink_ratio"] <= 1.0
    assert payload["ms"] >= 0
    assert payload["print_seconds"] > 0
    assert len(payload["image"]) > 100


@pytest.mark.parametrize("paper,width", [("58mm", 384), ("80mm", 576), ("custom", 512)])
def test_preview_paper_widths(api: Api, handle: str, paper: str, width: int) -> None:
    options = _default_options()
    options["paper"] = paper
    options["width_dots"] = width if paper == "custom" else None
    payload = api.preview(handle, options)
    assert payload["ok"] is True
    assert payload["width"] == width


def test_preview_invalid_option_is_reported_not_raised(api: Api, handle: str) -> None:
    payload = api.preview(handle, {**_default_options(), "gamma": 99})
    assert payload["ok"] is False
    assert "gamma" in payload["message"].lower()


def test_preview_unknown_handle(api: Api) -> None:
    payload = api.preview("nope", _default_options())
    assert payload["ok"] is False
    assert "expired" in payload["message"].lower()


def test_export_unknown_handle(api: Api) -> None:
    payload = api.export("nope", _default_options(), "png", True, {})
    assert payload["ok"] is False


def test_options_json_round_trip() -> None:
    """Exactly what crosses the bridge: dict -> ConvertOptions."""
    from thermaldots.models import ConvertOptions

    encoded = json.loads(json.dumps(_default_options()))
    opts = ConvertOptions.from_dict(encoded)
    assert opts.width_dots is None
    assert opts.resolved_width() == 384
    assert opts.auto_threshold is True


def test_export_signature_is_positional() -> None:
    """pywebview cannot pass keyword arguments to js_api methods."""
    parameters = list(inspect.signature(Api.export).parameters.values())[1:]
    assert [p.name for p in parameters] == [
        "handle",
        "options",
        "fmt",
        "sidecar",
        "escpos",
        "upscale",
    ]
    assert all(
        p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in parameters
    ), "keyword-only parameters break the JS bridge"
    assert [p.default for p in parameters[3:]] == [True, None, 1]


def test_other_api_methods_are_positional() -> None:
    for name in ("load_image", "preview", "bootstrap", "reveal_logs"):
        parameters = list(inspect.signature(getattr(Api, name)).parameters.values())[1:]
        for parameter in parameters:
            assert parameter.kind is not inspect.Parameter.KEYWORD_ONLY, name


def test_preview_reuses_decoded_image(api: Api, handle: str) -> None:
    """A slider drag must not re-decode the source on every tick."""
    import thermaldots.pipeline as pipeline_module

    pipeline_module.clear_cache()
    first = api.preview(handle, _default_options())
    second = api.preview(handle, {**_default_options(), "gamma": 1.6, "dither": "atkinson"})
    assert first["ok"] and second["ok"]
    assert len(pipeline_module._cache) == 1
    # Changing geometry legitimately needs a fresh fit.
    third = api.preview(handle, {**_default_options(), "paper": "80mm"})
    assert third["ok"]
    assert len(pipeline_module._cache) == 2


def test_preview_geometry_change_still_matches_engine(api: Api, handle: str) -> None:
    import thermaldots.pipeline as pipeline_module

    pipeline_module.clear_cache()
    first = api.preview(handle, _default_options())
    second = api.preview(handle, {**_default_options(), "paper": "80mm"})
    assert first["width"] == 384
    assert second["width"] == 576


def test_sources_are_capped(api: Api) -> None:
    from thermaldots.ui.app import MAX_SOURCES

    handles = [
        api.load_image(_data_url(), f"img{index}.png")["handle"] for index in range(MAX_SOURCES + 3)
    ]
    assert len(api._sources) == MAX_SOURCES
    assert handles[0] not in api._sources
    assert handles[-1] in api._sources
    expired = api.preview(handles[0], _default_options())
    assert expired["ok"] is False
    assert "expired" in expired["message"].lower()


def test_reveal_logs_reports_path(api: Api) -> None:
    payload = api.reveal_logs()
    assert payload["ok"] is True
    assert payload["path"].endswith("thermal-dots.log")


@pytest.mark.parametrize("fmt", ["png", "bmp", "bin", "txt"])
def test_export_writes_file_and_sidecar(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch, fmt: str
) -> None:
    target = tmp_path / f"out.{fmt}"
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: str(target))

    payload = api.export(handle, _default_options(), fmt, True, {"init": True, "feed": 2, "cut": True})

    assert payload["ok"] is True, payload
    assert payload["path"] == str(target)
    data = target.read_bytes()
    assert len(data) == payload["bytes"] > 0

    if fmt == "png":
        image = Image.open(io.BytesIO(data))
        assert image.mode == "1"
        assert image.size[0] == 384
    elif fmt == "bmp":
        assert Image.open(io.BytesIO(data)).mode == "1"
    elif fmt == "bin":
        assert data[:2] == b"\x1b@"
        assert data[2:6] == b"\x1dv0\x00"
        assert data[6:8] == (48).to_bytes(2, "little")
        assert data.endswith(b"\x1dV\x00")
    else:
        assert data.decode("utf-8").strip()

    sidecar = target.with_suffix(target.suffix + ".json")
    assert sidecar.exists()
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["format"] == fmt
    assert metadata["width"] == 384
    assert metadata["bytes"] == len(data)


def test_export_cancelled_dialog(api: Api, handle: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: None)
    payload = api.export(handle, _default_options(), "png", True, None)
    assert payload == {"ok": False, "cancelled": True}


def test_export_without_sidecar(api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "plain.png"
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: str(target))
    payload = api.export(handle, _default_options(), "png", False, None)
    assert payload["ok"] is True
    assert target.exists()
    assert not target.with_suffix(".png.json").exists()


def test_export_uses_engine_result_for_dither_choice(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file must match what the preview showed, not a default re-render."""
    target = tmp_path / "halftone.png"
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: str(target))
    options = {**_default_options(), "dither": "halftone", "paper": "80mm"}
    api.export(handle, options, "png", True, None)

    from thermaldots.models import ConvertOptions
    from thermaldots.pipeline import convert

    expected = convert(api._sources[handle], ConvertOptions.from_dict(options))
    assert Image.open(target).size == (576, expected.height)
    assert target.read_bytes() == expected.png_bytes(compress_level=6)


def test_export_upscale_writes_a_larger_raster(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "big.png"
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: str(target))

    payload = api.export(handle, _default_options(), "png", True, None, "2")

    assert payload["ok"] is True, payload
    assert payload["upscale"] == 2
    with Image.open(target) as image:
        assert image.size == (768, 576)
    assert payload["pixel_width"] == 768
    assert payload["pixel_height"] == 576


def test_export_upscale_is_rejected_for_bin(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Api, "_ask_save_path", lambda self, suggested, output_format: str(tmp_path / "x.bin")
    )
    payload = api.export(handle, _default_options(), "bin", True, None, 2)
    assert payload["ok"] is False
    assert "upscale only applies" in str(payload["message"])


def test_preview_render_native_marks_screen_export(
    api: Api, handle: str
) -> None:
    options = _default_options()
    options["render_width"] = WIDTH
    payload = api.preview(handle, options)
    assert payload["ok"] is True, payload
    assert payload["screen"] is True
    assert payload["width"] == WIDTH
    assert payload["height"] == HEIGHT
    image = Image.open(io.BytesIO(base64.b64decode(payload["image"].split(",", 1)[1])))
    assert image.size == (WIDTH, HEIGHT)


def test_export_render_native_writes_source_size(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "header.png"
    monkeypatch.setattr(Api, "_ask_save_path", lambda self, suggested, output_format: str(target))
    options = _default_options()
    options["render_width"] = WIDTH

    payload = api.export(handle, options, "png", True, None, 1)

    assert payload["ok"] is True, payload
    assert payload["screen"] is True
    with Image.open(target) as image:
        assert image.size == (WIDTH, HEIGHT)
    sidecar = json.loads(target.with_suffix(".png.json").read_text(encoding="utf-8"))
    assert sidecar["screen_export"] is True


def test_export_render_is_rejected_for_bin(
    api: Api, handle: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Api, "_ask_save_path", lambda self, suggested, output_format: str(tmp_path / "x.bin")
    )
    options = _default_options()
    options["render_width"] = WIDTH
    payload = api.export(handle, options, "bin", True, None, 1)
    assert payload["ok"] is False
    assert "render-width only applies" in str(payload["message"])
