"""Seam tests for cursor capture and highlight (ticket 06).

The seam under test is the ``screenrec`` console entry point: driven as a real
subprocess, a short recording with the cursor highlight on must produce a
complete, valid, decodable MP4 that includes the cursor annotation, and the
toggle-off path must produce a valid MP4 without it. Annotation presence is
verified by comparing a toggle-on recording against a toggle-off recording of
the same screen: the light-yellow highlight pixels that appear only in the ON
frame are the cursor annotation, and the comparison cancels screen content and
encoding artifacts.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from screenrec.cli.main import build_parser


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
    """Return the number of decoded video frames; raises via assert on invalid output."""
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


def decode_frame_bgra(path: Path) -> bytes:
    """Decode the first video frame as raw BGRA bytes via ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None, "ffmpeg is not installed"
    result = subprocess.run(
        [
            ffmpeg, "-v", "error", "-i", str(path),
            "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "bgra", "-",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"ffmpeg could not decode {path}: {result.stderr}"
    return result.stdout


def _is_highlight_pixel(data: bytes, i: int) -> bool:
    """Is the BGRA pixel at byte offset ``i`` the light-yellow highlight (approx)?"""
    b, g, r = data[i], data[i + 1], data[i + 2]
    return r > 230 and g > 230 and 100 <= b <= 210


def _count_highlight_only(on_data: bytes, off_data: bytes) -> int:
    """Count pixels highlight-yellow in the ON frame but not in the OFF frame.

    This is the cursor annotation: present when the highlight is on, absent when
    it is off.
    """
    count = 0
    for i in range(0, min(len(on_data), len(off_data)) - 3, 4):
        if _is_highlight_pixel(on_data, i) and not _is_highlight_pixel(off_data, i):
            count += 1
    return count


def _count_noise_only(on_data: bytes, off_data: bytes) -> int:
    """Count pixels highlight-yellow in OFF but not ON (screen change, no annotation)."""
    count = 0
    for i in range(0, min(len(on_data), len(off_data)) - 3, 4):
        if _is_highlight_pixel(off_data, i) and not _is_highlight_pixel(on_data, i):
            count += 1
    return count


needs_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None, reason="ffprobe is not installed"
)
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)

# The toggle-on annotation ring adds well over this many highlight pixels;
# screen-change noise between two back-to-back recordings stays well under it.
ANNOTATION_MIN_PIXELS = 40


def _record(tmp_path: Path, name: str, *extra: str) -> Path:
    output = tmp_path / f"{name}.mp4"
    result = run_screenrec(
        "--monitor", "1", "--duration", "1", "--fps", "15",
        "--output", str(output), *extra, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return output


@needs_ffprobe
@needs_ffmpeg
def test_cursor_highlight_recording_includes_annotation(tmp_path: Path) -> None:
    on = _record(tmp_path, "on", "--cursor-highlight")
    off = _record(tmp_path, "off", "--no-cursor-highlight")
    assert ffprobe_frames(on) > 0
    on_data = decode_frame_bgra(on)
    off_data = decode_frame_bgra(off)
    assert _count_highlight_only(on_data, off_data) >= ANNOTATION_MIN_PIXELS


@needs_ffprobe
@needs_ffmpeg
def test_no_cursor_highlight_recording_excludes_annotation(tmp_path: Path) -> None:
    off = _record(tmp_path, "off", "--no-cursor-highlight")
    on = _record(tmp_path, "on", "--cursor-highlight")
    assert ffprobe_frames(off) > 0
    off_data = decode_frame_bgra(off)
    on_data = decode_frame_bgra(on)
    # The ON baseline carries the annotation, so the comparison is meaningful.
    assert _count_highlight_only(on_data, off_data) >= ANNOTATION_MIN_PIXELS
    # OFF carries no annotation: highlight pixels unique to OFF are just
    # screen-change noise, far below the annotation threshold.
    assert _count_noise_only(on_data, off_data) < ANNOTATION_MIN_PIXELS


def test_cursor_highlight_defaults_to_on() -> None:
    args = build_parser().parse_args([])
    assert args.cursor_highlight is True


def test_no_cursor_highlight_flag_turns_it_off() -> None:
    args = build_parser().parse_args(["--no-cursor-highlight"])
    assert args.cursor_highlight is False
