"""In-process unit tests for the CLI assembly seam (assemble).

The wiring decisions (which source, which encoder, output path, preview) are
tested by monkeypatching the heavy constructors, so no display, mss or ffmpeg
is needed — the subprocess end-to-end tests stay as the real-platform layer.
"""

import argparse
from importlib import import_module

import pytest

from screenrec.capture import WindowMatch, WindowRect
from screenrec.cli.main import assemble, build_parser


class _FakeSource:
    """Answers the geometry assemble queries without a real display."""

    def __init__(self, *args, **kwargs):
        self.width = 100
        self.height = 100

    def capture_rect(self):
        return WindowRect(0, 0, 100, 100)

    def monitors(self):
        return []


class _FakeFullscreenSource(_FakeSource):
    pass


class _FakeRegionSource(_FakeSource):
    pass


class _FakeFfmpegEncoder:
    def __init__(self, *args, **kwargs):
        self.args = args


class _FakeNoopEncoder:
    def __init__(self, *args, **kwargs):
        self.args = args


class _FakePreview:
    def __init__(self, *args, **kwargs):
        self.args = args


def _patch(monkeypatch, tmp_path):
    # import_module: the package attribute "main" is the function, not the
    # module (cli/__init__.py rebinds it), so the string target would resolve
    # to the function and fail.
    cli_main = import_module("screenrec.cli.main")
    monkeypatch.setattr(cli_main, "FullscreenSource", _FakeFullscreenSource)
    monkeypatch.setattr(cli_main, "RegionSource", _FakeRegionSource)
    monkeypatch.setattr(cli_main, "FfmpegFrameEncoder", _FakeFfmpegEncoder)
    monkeypatch.setattr(cli_main, "NoopFrameEncoder", _FakeNoopEncoder)
    monkeypatch.setattr(cli_main, "OpenCvPreview", _FakePreview)
    monkeypatch.setattr(cli_main, "default_output_path", lambda: tmp_path / "rec.mp4")
    return cli_main


def _args(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def test_assemble_fullscreen_default_wires_ffmpeg(monkeypatch, tmp_path) -> None:
    _patch(monkeypatch, tmp_path)
    plan = assemble(_args())
    assert isinstance(plan.source, _FakeFullscreenSource)
    assert isinstance(plan.encoder, _FakeFfmpegEncoder)
    assert plan.output == tmp_path / "rec.mp4"
    assert plan.preview is None
    assert plan.preview_only is False


def test_assemble_region_source(monkeypatch, tmp_path) -> None:
    _patch(monkeypatch, tmp_path)
    plan = assemble(_args("--region", "10,20,30,40"))
    assert isinstance(plan.source, _FakeRegionSource)


def test_assemble_window_source(monkeypatch, tmp_path) -> None:
    cli_main = _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli_main, "find_window", lambda title: WindowMatch(WindowRect(0, 0, 50, 50))
    )
    plan = assemble(_args("--window", "Title"))
    assert isinstance(plan.source, _FakeRegionSource)


def test_assemble_preview_only_uses_noop_encoder(monkeypatch, tmp_path) -> None:
    _patch(monkeypatch, tmp_path)
    plan = assemble(_args("--preview-only"))
    assert isinstance(plan.encoder, _FakeNoopEncoder)
    assert plan.output is None
    assert plan.preview_only is True


def test_assemble_preview_constructs_preview(monkeypatch, tmp_path) -> None:
    _patch(monkeypatch, tmp_path)
    plan = assemble(_args("--preview"))
    assert isinstance(plan.preview, _FakePreview)


def test_assemble_invalid_source_raises(monkeypatch, tmp_path) -> None:
    cli_main = _patch(monkeypatch, tmp_path)

    class _BadRegionSource(_FakeRegionSource):
        def __init__(self, *args, **kwargs):
            raise ValueError("invalid region")

    monkeypatch.setattr(cli_main, "RegionSource", _BadRegionSource)
    with pytest.raises(ValueError, match="invalid region"):
        assemble(_args("--region", "0,0,10,10"))
