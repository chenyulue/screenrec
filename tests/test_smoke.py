"""Smoke tests for the screenrec console command.

The primary seam under test is the ``screenrec`` console entry point:
the installed command must run and print help/version output without
touching any capture or encoding machinery.
"""

import shutil
import subprocess

from screenrec import __version__


def run_screenrec(*args: str) -> subprocess.CompletedProcess:
    screenrec = shutil.which("screenrec")
    assert screenrec is not None, "screenrec console command is not installed"
    return subprocess.run(
        [screenrec, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_screenrec_help_prints_usage() -> None:
    result = run_screenrec("--help")

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "screenrec" in result.stdout


def test_screenrec_version_prints_package_version() -> None:
    result = run_screenrec("--version")

    assert result.returncode == 0
    assert "screenrec" in result.stdout
    assert __version__ in result.stdout
