"""Capture module: the capture backend boundary (per ADR 0002).

Owns the mss wrapper and the platform-specific window-resolution abstraction
that the rest of the pipeline consumes frames from. Fullscreen, region, and
window capture sources are implemented against this boundary.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

import mss


class WindowSource(ABC):
    """A source of raw screen frames for the recording pipeline."""

    @abstractmethod
    def grab(self) -> bytes:
        """Capture and return one raw frame."""
        ...


class FullscreenSource(WindowSource):
    """mss-backed fullscreen capture for a single monitor (raw BGRA frames)."""

    def __init__(self, monitor: int = 1) -> None:
        self._sct = mss.mss()
        monitors = self._sct.monitors
        # mss reserves index 0 for the virtual full-screen dummy entry.
        if not 1 <= monitor < len(monitors):
            raise ValueError(
                f"monitor {monitor} is out of range: 1..{len(monitors) - 1}"
            )
        self._monitor = monitors[monitor]

    @property
    def width(self) -> int:
        return self._monitor["width"]

    @property
    def height(self) -> int:
        return self._monitor["height"]

    def grab(self) -> bytes:
        return self._sct.grab(self._monitor).bgra


@dataclass(frozen=True)
class WindowRect:
    """A window's bounding rectangle on the virtual screen."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowMatch:
    """A located window: its bounding rect and an optional warning."""

    rect: WindowRect
    warning: str | None = None


class RegionSource(WindowSource):
    """mss-backed capture of an arbitrary rectangular region (raw BGRA frames)."""

    def __init__(self, rect: WindowRect) -> None:
        self._sct = mss.mss()
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError(
                f"invalid region {rect.left},{rect.top},{rect.width},{rect.height}: "
                "width and height must be positive"
            )
        virtual = self._sct.monitors[0]
        if (
            rect.left < virtual["left"]
            or rect.top < virtual["top"]
            or rect.left + rect.width > virtual["left"] + virtual["width"]
            or rect.top + rect.height > virtual["top"] + virtual["height"]
        ):
            raise ValueError(
                f"invalid region {rect.left},{rect.top},{rect.width},{rect.height}: "
                "region is outside the screen bounds"
            )
        self._rect = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
        }

    @property
    def width(self) -> int:
        return self._rect["width"]

    @property
    def height(self) -> int:
        return self._rect["height"]

    def grab(self) -> bytes:
        return self._sct.grab(self._rect).bgra


def find_window(title_substring: str) -> WindowMatch:
    """Locate the first window whose title contains the substring.

    Platform-specific window enumeration (pygetwindow on Windows, wmctrl on
    Linux X11) sits behind this boundary so callers never see platform
    differences. When several windows match, the first match is taken and a
    warning is returned.
    """
    if sys.platform == "win32":
        return _find_window_windows(title_substring)
    return _find_window_x11(title_substring)


def _find_window_windows(title_substring: str) -> WindowMatch:
    import pygetwindow

    matches = [
        WindowRect(window.left, window.top, window.width, window.height)
        for window in pygetwindow.getAllWindows()
        if title_substring.lower() in (window.title or "").lower()
    ]
    return _first_match(matches, title_substring)


def _find_window_x11(title_substring: str) -> WindowMatch:
    try:
        result = subprocess.run(
            ["wmctrl", "-lG"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        raise ValueError(
            "wmctrl is not installed; required for window capture on Linux"
        ) from None
    if result.returncode != 0:
        raise ValueError(f"wmctrl failed: {result.stderr.strip()}")

    # wmctrl -lG prints: window-id desktop-id x y width height hostname title.
    matches: list[WindowRect] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 8:
            continue
        _, _, left, top, width, height, _ = fields[:7]
        title = " ".join(fields[7:])
        if title_substring.lower() not in title.lower():
            continue
        try:
            matches.append(WindowRect(int(left), int(top), int(width), int(height)))
        except ValueError:
            continue

    return _first_match(matches, title_substring)


def _first_match(matches: list[WindowRect], title_substring: str) -> WindowMatch:
    if not matches:
        raise ValueError(f"no window matches title substring '{title_substring}'")
    return WindowMatch(matches[0], _multiple_match_warning(len(matches), title_substring))


def _multiple_match_warning(count: int, title_substring: str) -> str | None:
    if count <= 1:
        return None
    return (
        f"{count} windows match title substring '{title_substring}'; "
        "using the first"
    )
