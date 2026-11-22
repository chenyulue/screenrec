"""Capture module: the capture backend boundary (per ADR 0002).

Owns the mss wrapper and the platform-specific window-resolution abstraction
that the rest of the pipeline consumes frames from. Fullscreen, region, and
window capture sources are implemented against this boundary.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import mss
from mss.base import MSS

from screenrec.capture.cursor import CursorAnnotator


def _open_mss(cursor_highlight: bool) -> MSS:
    """Open an mss instance with cursor compositing where the platform supports it.

    ``with_cursor`` is a Linux-only mss feature; passing it on other
    platforms raises a DeprecationWarning from mss.
    """
    if sys.platform == "linux":
        return mss.mss(with_cursor=cursor_highlight)
    return mss.mss()

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


# Inset from a monitor's edge when placing the preview window on it.
PREVIEW_MARGIN = 20


def _monitor_overlaps(monitor: dict, rect: dict) -> bool:
    """Whether a monitor's rect intersects the captured rect."""
    return not (
        monitor["left"] + monitor["width"] <= rect["left"]
        or rect["left"] + rect["width"] <= monitor["left"]
        or monitor["top"] + monitor["height"] <= rect["top"]
        or rect["top"] + rect["height"] <= monitor["top"]
    )


class WindowSource(ABC):
    """A source of raw screen frames for the recording pipeline."""

    # Optional provider of a window rectangle to erase from every frame: a
    # callable returning WindowRect | None. The session wires the preview
    # window here, so the capture never shows (or records) itself.
    exclude: Callable[[], WindowRect | None] | None = None
    @abstractmethod
    def grab(self) -> bytes:
        """Capture and return one raw frame."""
        ...

    def preview_position(self) -> tuple[int, int] | None:
        """Recommended top-left for the preview window: a monitor the capture
        does not touch, or None when there is no spare monitor."""
        return None


def _erase_excluded_window(
    frame: bytearray,
    width: int,
    height: int,
    left: int,
    top: int,
    exclude: Callable[[], WindowRect | None] | None,
) -> None:
    """Paint the excluded window's rectangle black, in place.

    The preview window sits on the screen being captured; without this the
    preview would show itself inside itself, a recursive preview. ``exclude``
    returns the window's rect on the virtual screen (or None when there is
    nothing to exclude); its coordinates are mapped into the frame's local
    space and clipped to it.
    """
    if exclude is None:
        return
    rect = exclude()
    if rect is None:
        return
    x0 = max(rect.left - left, 0)
    y0 = max(rect.top - top, 0)
    x1 = min(rect.left + rect.width - left, width)
    y1 = min(rect.top + rect.height - top, height)
    if x0 >= x1 or y0 >= y1:
        return  # excluded window is outside the captured area
    for row in range(y0, y1):
        start = (row * width + x0) * 4
        frame[start : start + (x1 - x0) * 4] = b"\x00" * ((x1 - x0) * 4)


class FullscreenSource(WindowSource):
    """mss-backed fullscreen capture for a single monitor (raw BGRA frames)."""

    def __init__(
        self,
        monitor: int = 1,
        cursor_highlight: bool = True,
        exclude: Callable[[], WindowRect | None] | None = None,
    ) -> None:
        self._sct = _open_mss(cursor_highlight)
        monitors = self._sct.monitors
        # mss reserves index 0 for the virtual full-screen dummy entry.
        if not 1 <= monitor < len(monitors):
            raise ValueError(
                f"monitor {monitor} is out of range: 1..{len(monitors) - 1}"
            )
        self._monitor = monitors[monitor]
        self._monitor_index = monitor
        self._annotator = CursorAnnotator(
            self._monitor["width"],
            self._monitor["height"],
            self._monitor["left"],
            self._monitor["top"],
            enabled=cursor_highlight,
        )
        self.exclude = exclude


    @property
    def width(self) -> int:
        return self._monitor["width"]

    @property
    def height(self) -> int:
        return self._monitor["height"]

    def grab(self) -> bytes:
        shot = self._sct.grab(self._monitor)
        # Annotate the reused mss buffer in place, then hand the session a
        # private copy.
        frame = self._annotator.annotate(shot.raw)
        _erase_excluded_window(
            frame,
            self._monitor["width"],
            self._monitor["height"],
            self._monitor["left"],
            self._monitor["top"],
            self.exclude,
        )
        return bytes(frame)

    def preview_position(self) -> tuple[int, int] | None:
        """Top-left of the first physical monitor that is not being recorded."""
        for index, candidate in enumerate(self._sct.monitors):
            if index in (0, self._monitor_index):
                continue
            return (
                candidate["left"] + PREVIEW_MARGIN,
                candidate["top"] + PREVIEW_MARGIN,
            )
        return None


class RegionSource(WindowSource):
    """mss-backed capture of an arbitrary rectangular region (raw BGRA frames)."""

    def __init__(
        self,
        rect: WindowRect,
        cursor_highlight: bool = True,
        exclude: Callable[[], WindowRect | None] | None = None,
    ) -> None:
        self._sct = _open_mss(cursor_highlight)
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
        self._annotator = CursorAnnotator(
            rect.width, rect.height, rect.left, rect.top, enabled=cursor_highlight
        )
        self.exclude = exclude


    @property
    def width(self) -> int:
        return self._rect["width"]

    @property
    def height(self) -> int:
        return self._rect["height"]

    def grab(self) -> bytes:
        shot = self._sct.grab(self._rect)
        frame = self._annotator.annotate(shot.raw)
        _erase_excluded_window(
            frame,
            self._rect["width"],
            self._rect["height"],
            self._rect["left"],
            self._rect["top"],
            self.exclude,
        )
        return bytes(frame)

    def preview_position(self) -> tuple[int, int] | None:
        """Top-left of the first physical monitor the captured region misses."""
        for candidate in self._sct.monitors[1:]:
            if not _monitor_overlaps(candidate, self._rect):
                return (
                    candidate["left"] + PREVIEW_MARGIN,
                    candidate["top"] + PREVIEW_MARGIN,
                )
        return None


def list_windows() -> list[tuple[str, WindowRect]]:
    """Enumerate all top-level windows as (title, bounding rect) pairs.

    Backs ``--list-windows`` so the user can pick a target for ``--window``.
    Platform-specific enumeration sits behind this boundary, same as
    ``find_window``, so callers never see platform differences.
    """
    if sys.platform == "win32":
        return _list_windows_windows()
    return _list_windows_x11()


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


def _list_windows_windows() -> list[tuple[str, WindowRect]]:
    import pygetwindow
    return [
        (window.title, WindowRect(window.left, window.top, window.width, window.height))
        for window in pygetwindow.getAllWindows()
        if (window.title or "").strip()
    ]


def _find_window_windows(title_substring: str) -> WindowMatch:
    matches = [
        rect
        for title, rect in _list_windows_windows()
        if title_substring.lower() in title.lower()
    ]
    return _first_match(matches, title_substring)


def _list_windows_x11() -> list[tuple[str, WindowRect]]:
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
    windows: list[tuple[str, WindowRect]] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 8:
            continue
        _, _, left, top, width, height, _ = fields[:7]
        title = " ".join(fields[7:])
        if not title.strip():
            continue
        try:
            rect = WindowRect(int(left), int(top), int(width), int(height))
        except ValueError:
            continue
        windows.append((title, rect))
    return windows


def _find_window_x11(title_substring: str) -> WindowMatch:
    matches = [
        rect
        for title, rect in _list_windows_x11()
        if title_substring.lower() in title.lower()
    ]
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
