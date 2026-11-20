"""Seam tests for fullscreen recording (ticket 02).

The seam under test is the ``screenrec`` console entry point: driven as a real
subprocess, it records the screen for a chosen duration and must produce a
complete, valid, decodable MP4. Assertions cover external behavior only —
process exit codes, output files, and user-facing error messages.
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest


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
def _assert_single_valid_recording(tmp_path: Path) -> None:
    files = list((tmp_path / "recordings").glob("rec-*.mp4"))
    assert len(files) == 1
    assert re.fullmatch(r"rec-\d{8}-\d{6}\.mp4", files[0].name)
    assert ffprobe_frames(files[0]) > 0


def _drive_stop_trigger(proc: subprocess.Popen, trigger: Callable[[subprocess.Popen], None]) -> int:
    """Let the recording run, fire the stop trigger, wait for graceful exit."""
    time.sleep(3)
    trigger(proc)
    try:
        return proc.wait(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()

@needs_ffprobe
def test_duration_records_fullscreen_and_produces_valid_mp4(tmp_path: Path) -> None:
    result = run_screenrec("--monitor", "1", "--duration", "1", "--fps", "15", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    _assert_single_valid_recording(tmp_path)


@needs_ffprobe
def test_output_flag_overrides_default_path(tmp_path: Path) -> None:
    output = tmp_path / "custom" / "my-rec.mp4"
    result = run_screenrec(
        "--duration", "1", "--fps", "15", "--output", str(output), cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert ffprobe_frames(output) > 0
    assert not (tmp_path / "recordings").exists()


@needs_ffprobe
def test_fps_option_controls_frame_rate(tmp_path: Path) -> None:
    low = tmp_path / "low.mp4"
    high = tmp_path / "high.mp4"

    for path, fps in ((low, 10), (high, 30)):
        result = run_screenrec(
            "--duration", "2", "--fps", str(fps), "--output", str(path), cwd=tmp_path
        )
        assert result.returncode == 0, result.stderr

    assert ffprobe_frames(high) > ffprobe_frames(low)


@needs_ffprobe
@pytest.mark.skipif(sys.platform != "posix", reason="SIGINT test needs POSIX signals")
def test_ctrl_c_triggers_graceful_stop(tmp_path: Path) -> None:
    screenrec = shutil.which("screenrec")
    assert screenrec is not None
    proc = subprocess.Popen(
        [screenrec, "--fps", "15"],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    returncode = _drive_stop_trigger(proc, lambda p: p.send_signal(signal.SIGINT))

    assert returncode == 0
    _assert_single_valid_recording(tmp_path)


@needs_ffprobe
def test_enter_triggers_graceful_stop(tmp_path: Path) -> None:
    screenrec = shutil.which("screenrec")
    assert screenrec is not None
    proc = subprocess.Popen(
        [screenrec, "--fps", "15"],
        cwd=str(tmp_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    assert proc.stdin is not None

    def trigger(p: subprocess.Popen) -> None:
        assert p.stdin is not None
        p.stdin.write("\n")
        p.stdin.flush()
        p.stdin.close()

    returncode = _drive_stop_trigger(proc, trigger)

    assert returncode == 0
    _assert_single_valid_recording(tmp_path)


def test_invalid_fps_is_rejected(tmp_path: Path) -> None:
    for fps in ("0", "61"):
        result = run_screenrec("--duration", "1", "--fps", fps, cwd=tmp_path)
        assert result.returncode != 0
        assert "fps" in (result.stderr + result.stdout).lower()


def test_invalid_monitor_fails_with_clear_error(tmp_path: Path) -> None:
    result = run_screenrec("--monitor", "999", cwd=tmp_path)
    assert result.returncode != 0
    assert "monitor" in result.stderr.lower()


def test_broken_ffmpeg_binary_fails_with_clear_error(tmp_path: Path) -> None:
    # sys.executable cannot parse the ffmpeg argument list, so the encoder
    # process dies immediately and the session must report a fatal stop.
    result = run_screenrec(
        "--duration", "1", env={"IMAGEIO_FFMPEG_EXE": sys.executable}, cwd=tmp_path
    )
    assert result.returncode != 0
    assert result.stderr.strip()
