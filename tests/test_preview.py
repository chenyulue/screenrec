"""Seam tests for the live preview window (ticket 07).

Three seams are exercised:
- The ``screenrec`` console entry point, driven as a real subprocess, for the
  external behavior: ``--preview`` records a valid MP4 without breaking the
  recording flow, and ``--preview-only`` shows the capture without writing a
  file.
- ``DefaultRecordingSession`` itself, with a fake preview injected, for the
  q-to-quit graceful-stop logic (no platform display needed).
- The capture sources' preview-window exclusion (no display needed): the
  preview window's rect must be painted out of every grabbed frame.
"""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import cast

import cv2
import pytest
from mss.base import MSS

from screenrec.capture import (
    RegionSource,
    WindowRect,
    WindowSource,
)
from screenrec.cli.main import build_parser
from screenrec.encoder import FrameEncoder
from screenrec.preview import PREVIEW_MARGIN, OpenCvPreview, Preview, resolve_placement
from screenrec.session import DefaultRecordingSession

# --------------------------------------------------------------------------- #
# Parser tests
# --------------------------------------------------------------------------- #


def test_preview_defaults_to_off() -> None:
    args = build_parser().parse_args([])
    assert args.preview is False
    assert args.preview_only is False


def test_preview_flag_turns_it_on() -> None:
    args = build_parser().parse_args(["--preview"])
    assert args.preview is True


def test_preview_only_flag_sets_preview_only() -> None:
    args = build_parser().parse_args(["--preview-only"])
    assert args.preview_only is True


# --------------------------------------------------------------------------- #
# Session unit tests (fake preview — no display required)
# --------------------------------------------------------------------------- #


class _NeverFails(WindowSource):
    """A capture source that produces a fixed frame forever."""

    def grab(self) -> bytes:
        return b"\x00" * 16

    def capture_rect(self) -> WindowRect:
        return WindowRect(0, 0, 4, 4)

    def monitors(self) -> list[dict]:
        return []


class _RecordingEncoder(FrameEncoder):
    """Records pushed frames and whether finalize ran."""

    def __init__(self) -> None:
        self.pushed: list[bytes] = []
        self.finalized = False

    def push(self, frame: bytes) -> None:
        self.pushed.append(frame)

    def finalize(self) -> None:
        self.finalized = True


class _FakePreview(Preview):
    """A fake preview that requests quit after ``quit_after`` shown frames."""

    def __init__(self, quit_after: int) -> None:
        self._quit_after = quit_after
        self._shown = 0
        self._quit = False
        self.closed = False
        # No real window, but a fixed rect the session can wire in; set to
        # None to simulate a window that cannot be located.
        self.rect: WindowRect | None = WindowRect(0, 0, 1, 1)

    def show(self, frame: bytes) -> None:
        self._shown += 1
        if self._shown >= self._quit_after:
            self._quit = True

    def quit_requested(self) -> bool:
        return self._quit

    def prepare(self) -> WindowRect | None:
        """Return the fake's fixed rect (or None when it is unset)."""
        return self.rect

    def close(self) -> None:
        self.closed = True


def _run_to_completion(session: DefaultRecordingSession, timeout: float = 10.0) -> None:
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"session did not stop within {timeout}s"


def test_preview_q_triggers_graceful_stop() -> None:
    """Pressing q in the preview requests a graceful stop and finalizes."""
    preview = _FakePreview(quit_after=3)
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(_NeverFails(), encoder, fps=30, preview=preview)

    _run_to_completion(session)

    assert session.error is None
    assert preview.quit_requested(), "preview should have requested quit"
    assert preview.closed, "preview window must be closed on stop"
    assert encoder.finalized, "graceful stop must finalize the encoder"


def test_no_preview_does_not_touch_display() -> None:
    """With preview off, the session records and finalizes normally."""
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(
        _NeverFails(), encoder, fps=30, duration=0.1
    )

    session.start()
    session.run()

    assert session.error is None
    assert encoder.finalized


# --------------------------------------------------------------------------- #
# Preview-window exclusion tests (capture must never see the preview itself)
# --------------------------------------------------------------------------- #


class _FakeSct:
    """Stands in for the mss instance: fixed monitors and a fixed shot."""

    def __init__(
        self, raw: bytearray | None = None, monitors: list[dict] | None = None
    ) -> None:
        self._raw = raw if raw is not None else bytearray(b"\x00" * 16)
        self.monitors = monitors if monitors is not None else _SINGLE_MONITOR

    def grab(self, _rect: object):
        return _FakeShot(self._raw)


class _FakeShot:
    def __init__(self, raw: bytearray) -> None:
        self.raw = raw

# mss-style monitor tables: index 0 is the virtual screen, the rest are
# physical monitors.
_SINGLE_MONITOR = [
    {"left": 0, "top": 0, "width": 1920, "height": 1080},
]
_TWO_MONITORS = [
    {"left": 0, "top": 0, "width": 3840, "height": 1080},
    {"left": 0, "top": 0, "width": 1920, "height": 1080},
    {"left": 1920, "top": 0, "width": 1920, "height": 1080},
]


def _white_frame(width: int, height: int) -> bytearray:
    return bytearray(bytes((255, 255, 255, 255)) * width * height)


def _pixel(frame: bytes, x: int, y: int, width: int) -> bytes:
    i = (y * width + x) * 4
    return frame[i : i + 4]


def test_preview_window_is_erased_from_captured_frames() -> None:
    """The preview window's rect is painted black, so frames cannot show it."""
    w, h = 32, 24
    source = RegionSource(WindowRect(0, 0, w, h), cursor_highlight=False)
    source._sct = cast(MSS, _FakeSct(_white_frame(w, h)))
    source.set_exclude(WindowRect(10, 8, 4, 3))
    frame = source.grab()
    for y in range(8, 11):
        for x in range(10, 14):
            assert _pixel(frame, x, y, w) == b"\x00\x00\x00\x00"
    # Pixels outside the excluded window stay untouched.
    assert _pixel(frame, 0, 0, w) == b"\xff\xff\xff\xff"
    assert _pixel(frame, 9, 8, w) == b"\xff\xff\xff\xff"
    assert _pixel(frame, 10, 7, w) == b"\xff\xff\xff\xff"


def test_excluded_window_outside_capture_is_noop() -> None:
    """A window rect outside the captured area leaves the frame untouched."""
    w, h = 32, 24
    frame = _white_frame(w, h)
    source = RegionSource(WindowRect(0, 0, w, h), cursor_highlight=False)
    source._sct = cast(MSS, _FakeSct(frame))
    source.set_exclude(WindowRect(100, 100, 4, 3))
    assert bytes(source.grab()) == bytes(frame)


def test_session_wires_preview_window_as_capture_exclude() -> None:
    """With a preview, the session excludes the window from the source."""
    preview = _FakePreview(quit_after=1)
    source = _NeverFails()
    session = DefaultRecordingSession(
        source, _RecordingEncoder(), fps=30, preview=preview
    )
    session.start()
    try:
        assert source._exclude == preview.rect
    finally:
        session.request_stop()
        session.stop()


def test_session_refuses_to_start_when_preview_rect_unavailable() -> None:
    """A preview window that cannot be located is a hard failure: recording
    with it would capture the preview inside its own frames."""
    preview = _FakePreview(quit_after=1)
    preview.rect = None
    session = DefaultRecordingSession(
        _NeverFails(), _RecordingEncoder(), fps=30, preview=preview
    )
    with pytest.raises(RuntimeError, match="preview window could not be located"):
        session.start()


class _ExcludeCheckSource(WindowSource):
    """Records the exclude rect seen at the first grab."""

    def __init__(self) -> None:
        self.seen: WindowRect | None = None

    def grab(self) -> bytes:
        self.seen = self._exclude
        return b"\x00" * 16

    def capture_rect(self) -> WindowRect:
        return WindowRect(0, 0, 4, 4)

    def monitors(self) -> list[dict]:
        return []


def test_exclude_is_set_before_the_first_captured_frame() -> None:
    """Regression for the first-frames hole: the preview rect is wired into
    the source before the capture thread can grab a single frame."""
    preview = _FakePreview(quit_after=5)
    source = _ExcludeCheckSource()
    session = DefaultRecordingSession(
        source, _RecordingEncoder(), fps=30, preview=preview
    )
    _run_to_completion(session)
    assert source.seen == preview.rect


def test_fullscreen_capture_places_preview_on_spare_monitor() -> None:
    """Fullscreen capture places the preview on a monitor it does not touch."""
    capture_rect = WindowRect(0, 0, 1920, 1080)
    assert resolve_placement(capture_rect, _TWO_MONITORS) == (
        1920 + PREVIEW_MARGIN,
        PREVIEW_MARGIN,
    )


def test_no_spare_monitor_leaves_preview_without_position() -> None:
    """A single monitor leaves the preview on the captured screen."""
    assert resolve_placement(WindowRect(0, 0, 1920, 1080), _SINGLE_MONITOR) is None


def test_region_capture_places_preview_on_untouched_monitor() -> None:
    """Region capture places the preview on a monitor the region does not touch."""
    assert resolve_placement(WindowRect(0, 0, 32, 24), _TWO_MONITORS) == (
        1920 + PREVIEW_MARGIN,
        PREVIEW_MARGIN,
    )


def test_capture_touching_every_monitor_has_no_placement() -> None:
    """A capture touching every monitor leaves the preview on the captured screen."""
    monitors = [
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": -10, "top": -10, "width": 1920, "height": 1080},
    ]
    assert resolve_placement(WindowRect(0, 0, 32, 24), monitors) is None


# --------------------------------------------------------------------------- #
# CLI subprocess seam tests
# --------------------------------------------------------------------------- #


def run_screenrec(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    screenrec = shutil.which("screenrec")
    assert screenrec is not None, "screenrec console command is not installed"
    full_env = dict(os.environ)
    return subprocess.run(
        [screenrec, *args],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def ffprobe_frames(path: Path) -> int:
    ffprobe = shutil.which("ffprobe")
    assert ffprobe is not None, "ffprobe is not installed"
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"ffprobe could not decode {path}: {result.stderr}"
    return int(result.stdout.strip())


needs_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None, reason="ffprobe is not installed"
)


@needs_ffprobe
def test_preview_recording_produces_valid_mp4(tmp_path: Path) -> None:
    """--preview records a valid MP4; the preview path does not break recording."""
    output = tmp_path / "preview.mp4"
    result = run_screenrec(
        "--monitor", "1", "--duration", "1", "--fps", "15",
        "--preview", "--output", str(output), cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert ffprobe_frames(output) > 0


def test_preview_only_writes_no_file(tmp_path: Path) -> None:
    """--preview-only shows the capture live and writes no video file."""
    result = run_screenrec(
        "--monitor", "1", "--duration", "1", "--fps", "15",
        "--preview-only", cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "recordings").exists()
    assert not list(tmp_path.glob("*.mp4"))


# --------------------------------------------------------------------------- #
# OpenCvPreview window-position tests (no display needed; cv2 is faked)
# --------------------------------------------------------------------------- #


def test_preview_prepare_maps_window_and_applies_position(monkeypatch) -> None:
    """The requested window position is applied once the window is mapped.

    On Linux GTK the window manager ignores move requests for unmapped
    windows, so prepare() — not construction — maps the window, applies the
    move and reads the rect back.
    """
    moves: list[tuple[int, int]] = []

    def fake_move(name: str, x: int, y: int) -> None:
        moves.append((x, y))

    monkeypatch.setattr(cv2, "namedWindow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "resizeWindow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "imshow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "moveWindow", fake_move)
    monkeypatch.setattr(cv2, "getWindowImageRect", lambda name: (100, 200, 8, 6))
    monkeypatch.setattr(cv2, "waitKey", lambda ms: 0)

    preview = OpenCvPreview(8, 6, position=(100, 200))
    # Best-effort move at construction time.
    assert moves == [(100, 200)]

    assert preview.prepare() == WindowRect(100, 200, 8, 6)
    # The window is mapped now, so the move is applied once.
    assert moves == [(100, 200), (100, 200)]

    preview.show(bytes((255, 255, 255, 255) * 8 * 6))
    # Showing frames never moves the window again.
    assert moves == [(100, 200), (100, 200)]


def test_preview_prepare_returns_none_when_rect_unavailable(monkeypatch) -> None:
    """A window that cannot be located reports None, so the session refuses
    to record with the preview inside the captured area."""
    monkeypatch.setattr(cv2, "namedWindow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "resizeWindow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "imshow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "moveWindow", lambda *args, **kwargs: None)
    monkeypatch.setattr(cv2, "getWindowImageRect", lambda name: (0, 0, 0, 0))
    monkeypatch.setattr(cv2, "waitKey", lambda ms: 0)

    preview = OpenCvPreview(8, 6)
    assert preview.prepare() is None
