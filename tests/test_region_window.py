"""Seam tests for region and window capture (ticket 03).

The seam under test is the ``screenrec`` console entry point: driven as a real
subprocess, it records a rectangular region or a specific window for a chosen
duration and must produce a complete, valid, decodable MP4. Invalid region
coordinates and non-existent windows must fail at startup with a clear error
and a non-zero exit code. Assertions cover external behavior only — process
exit codes, output files, and user-facing messages.
"""

import os
import shutil
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

import pytest

from screenrec.capture import find_window, list_windows
from screenrec.cli.main import build_parser


def run_screenrec(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    screenrec = shutil.which("screenrec")
    assert screenrec is not None, "screenrec console command is not installed"
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
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


needs_ffprobe = pytest.mark.skipif(
    shutil.which("ffprobe") is None, reason="ffprobe is not installed"
)

HELPER = Path(__file__).parent / "open_window.py"
WINDOW_TITLE = "screenrec-test-window"

_PS_HELPER = (
    "$count = __COUNT__;"
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$forms = 1..$count | ForEach-Object {"
    "  $f = New-Object System.Windows.Forms.Form;"
    "  $f.Text = 'screenrec-test-window-' + $_;"
    "  $f.Show();"
    "};"
    "Write-Output 'READY';"
    "Start-Sleep -Seconds 120"
)


def _start_window_helper(count: int) -> subprocess.Popen:
    """Open `count` windows titled screenrec-test-window-N and wait until ready."""
    if sys.platform == "win32":
        cmd = [
            "powershell", "-NoProfile", "-Command",
            _PS_HELPER.replace("__COUNT__", str(count)),
        ]
    else:
        cmd = [sys.executable, str(HELPER), str(count)]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert proc.stdout is not None
    ready = proc.stdout.readline()
    assert ready.strip() == "READY", (
        f"window helper did not report ready: {ready!r}"
        f"{proc.stderr.read() if proc.stderr else ''}"
    )
    return proc


def _assert_single_valid_recording(tmp_path: Path) -> None:
    files = list((tmp_path / "recordings").glob("rec-*.mp4"))
    assert len(files) == 1
    assert ffprobe_frames(files[0]) > 0


@needs_ffprobe
def test_region_recording_produces_valid_mp4(tmp_path: Path) -> None:
    result = run_screenrec(
        "--region", "100,100,200,150", "--duration", "1", "--fps", "15", cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    _assert_single_valid_recording(tmp_path)


def test_invalid_region_format_is_rejected(tmp_path: Path) -> None:
    for region in ("abc", "1,2,3", "1,2,3,4,5"):
        result = run_screenrec("--region", region, "--duration", "1", cwd=tmp_path)

        assert result.returncode != 0
        assert "region" in (result.stderr + result.stdout).lower()


def test_invalid_region_coordinates_fail_with_clear_error(tmp_path: Path) -> None:
    for region in ("100,100,0,100", "100,100,100,-50", "99999,99999,100,100"):
        result = run_screenrec("--region", region, "--duration", "1", cwd=tmp_path)

        assert result.returncode != 0
        assert "region" in result.stderr.lower()


def test_nonexistent_window_fails_with_clear_error(tmp_path: Path) -> None:
    result = run_screenrec(
        "--window", "screenrec-no-such-window-xyz", "--duration", "1", cwd=tmp_path
    )

    assert result.returncode != 0
    assert "window" in result.stderr.lower()


def test_list_windows_flag_is_parsed() -> None:
    args = build_parser().parse_args(["--list-windows"])
    assert args.list_windows is True


def test_list_windows_shows_open_window_titles(tmp_path: Path) -> None:
    """--list-windows lists window titles (with rects) and exits without recording."""
    helper = _start_window_helper(1)
    try:
        result = run_screenrec("--list-windows", cwd=tmp_path)
    finally:
        helper.terminate()
    assert result.returncode == 0, result.stderr
    assert WINDOW_TITLE in result.stdout


def test_window_enumeration_ensures_dpi_aware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Window enumeration must make the process DPI-aware first.

    Regression test for scaled displays: GetWindowRect reports logical pixels
    in a DPI-unaware process, while mss captures physical pixels, so window
    rects were misaligned with the recorded frames at any scaling other than
    100%.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        "screenrec.capture._ensure_dpi_aware", lambda: calls.append("dpi")
    )
    with pytest.raises(ValueError):
        find_window("screenrec-no-such-window-xyz")
    assert calls == ["dpi"]

    calls.clear()
    with suppress(ValueError):  # platform enumeration may fail; _ensure_dpi_aware already ran
        list_windows()
    assert calls == ["dpi"]


@needs_ffprobe
def test_window_capture_produces_valid_mp4(tmp_path: Path) -> None:
    helper = _start_window_helper(1)
    try:
        result = run_screenrec(
            "--window", WINDOW_TITLE, "--duration", "1", "--fps", "15", cwd=tmp_path
        )
    finally:
        helper.terminate()

    assert result.returncode == 0, result.stderr
    _assert_single_valid_recording(tmp_path)


@needs_ffprobe
def test_multiple_window_matches_warn_and_use_first(tmp_path: Path) -> None:
    helper = _start_window_helper(2)
    try:
        result = run_screenrec(
            "--window", WINDOW_TITLE, "--duration", "1", "--fps", "15", cwd=tmp_path
        )
    finally:
        helper.terminate()

    assert result.returncode == 0, result.stderr
    assert "warning" in result.stderr.lower()
    _assert_single_valid_recording(tmp_path)
