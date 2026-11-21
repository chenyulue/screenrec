"""Seam tests for the live preview window (ticket 07).

Two seams are exercised:
- The ``screenrec`` console entry point, driven as a real subprocess, for the
  external behavior: ``--preview`` records a valid MP4 without breaking the
  recording flow, and ``--preview-only`` shows the capture without writing a
  file.
- ``DefaultRecordingSession`` itself, with a fake preview injected, for the
  q-to-quit graceful-stop logic (no platform display needed).
"""

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from screenrec.capture import WindowSource
from screenrec.cli.main import build_parser
from screenrec.encoder import FrameEncoder
from screenrec.preview import Preview
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

    def show(self, frame: bytes) -> None:
        self._shown += 1
        if self._shown >= self._quit_after:
            self._quit = True

    def quit_requested(self) -> bool:
        return self._quit

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
