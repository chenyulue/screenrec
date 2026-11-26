"""Capture module: the capture backend boundary (per ADR 0002).

Owns the mss wrapper and the platform-specific window-resolution abstraction
that the rest of the pipeline consumes frames from. Fullscreen, region, and
window capture sources are implemented against this boundary.
"""

import ctypes
import subprocess
import sys
from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass

import mss
from mss.base import MSS
from mss.screenshot import ScreenShot

from screenrec.capture.cursor import CursorAnnotator
from screenrec.capture.cursor.platform import current_cursor, mss_composites_cursor


def _open_mss(cursor_highlight: bool) -> MSS:
    """Open an mss instance with cursor compositing where the platform supports it.

    ``with_cursor`` is a Linux-only mss feature; passing it on other
    platforms raises a DeprecationWarning from mss.
    """
    if mss_composites_cursor():
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


class WindowSource(ABC):
    """A source of raw screen frames for the recording pipeline."""

    # Window rectangle painted out of every frame. Set once by the recording
    # session via ``set_exclude`` before the capture thread starts, so the
    # capture thread only ever reads a fixed value.
    _exclude: WindowRect | None = None

    def set_exclude(self, rect: WindowRect | None) -> None:
        """Set the window rectangle to erase from every frame."""
        self._exclude = rect

    @property
    def width(self) -> int:
        """Frame width in pixels, derived from the captured rect."""
        return self.capture_rect().width

    @property
    def height(self) -> int:
        """Frame height in pixels, derived from the captured rect."""
        return self.capture_rect().height

    @abstractmethod
    def grab(self) -> bytes:
        """Capture and return one raw frame."""
        ...

    @abstractmethod
    def capture_rect(self) -> WindowRect:
        """The area of the virtual screen this source captures."""
        ...

    @abstractmethod
    def monitors(self) -> list[dict]:
        """The virtual screen's monitor table (mss monitor dicts)."""
        ...


class _MssFrameSource(WindowSource):
    """Shared frame preparation for all mss-backed sources.

    Cursor annotation and preview-window erasure collapse into one
    ``prepare_frame`` step, so a new source cannot forget the erase that
    keeps the preview out of the recording.
    """

    # Set by each subclass once its captured rect is known.
    _annotator: CursorAnnotator

    def __init__(self, cursor_highlight: bool, *, sct: MSS | None = None) -> None:
        # Injected mss backend (tests supply a fake); opened for real by default.
        self._sct = sct if sct is not None else _open_mss(cursor_highlight)

    def monitors(self) -> list[dict]:
        return self._sct.monitors


    def prepare_frame(self, shot: ScreenShot) -> bytes:
        """Annotate the reused mss buffer in place, erase the excluded
        window, then hand the caller a private copy."""
        rect = self.capture_rect()
        frame = self._annotator.annotate(shot.raw)
        _erase_excluded_window(
            frame,
            rect.width,
            rect.height,
            rect.left,
            rect.top,
            self._exclude,
        )
        return bytes(frame)

def _erase_excluded_window(
    frame: bytearray,
    width: int,
    height: int,
    left: int,
    top: int,
    exclude: WindowRect | None,
) -> None:
    """Paint the excluded window's rectangle black, in place.

    The preview window sits on the screen being captured; without this the
    preview would show itself inside itself, a recursive preview. ``exclude``
    is the window's rect on the virtual screen (or None when there is
    nothing to exclude); its coordinates are mapped into the frame's local
    space and clipped to it.
    """
    if exclude is None:
        return
    x0 = max(exclude.left - left, 0)
    y0 = max(exclude.top - top, 0)
    x1 = min(exclude.left + exclude.width - left, width)
    y1 = min(exclude.top + exclude.height - top, height)
    if x0 >= x1 or y0 >= y1:
        return  # excluded window is outside the captured area
    for row in range(y0, y1):
        start = (row * width + x0) * 4
        frame[start : start + (x1 - x0) * 4] = b"\x00" * ((x1 - x0) * 4)


class FullscreenSource(_MssFrameSource):
    """mss-backed fullscreen capture for a single monitor (raw BGRA frames)."""

    def __init__(
        self,
        monitor: int = 1,
        cursor_highlight: bool = True,
        *,
        sct: MSS | None = None,
    ) -> None:
        super().__init__(cursor_highlight, sct=sct)
        monitors = self._sct.monitors
        # mss reserves index 0 for the virtual full-screen dummy entry.
        if not 1 <= monitor < len(monitors):
            raise ValueError(
                f"monitor {monitor} is out of range: 1..{len(monitors) - 1}"
            )
        self._monitor = monitors[monitor]
        self._annotator = CursorAnnotator(
            self._monitor["width"],
            self._monitor["height"],
            current_cursor,
            left=self._monitor["left"],
            top=self._monitor["top"],
            enabled=cursor_highlight,
        )

    def grab(self) -> bytes:
        return self.prepare_frame(self._sct.grab(self._monitor))

    def capture_rect(self) -> WindowRect:
        """The recorded monitor's rect on the virtual screen."""
        monitor = self._monitor
        return WindowRect(
            monitor["left"], monitor["top"], monitor["width"], monitor["height"]
        )


class RegionSource(_MssFrameSource):
    """mss-backed capture of an arbitrary rectangular region (raw BGRA frames)."""

    def __init__(
        self,
        rect: WindowRect,
        cursor_highlight: bool = True,
        *,
        sct: MSS | None = None,
    ) -> None:
        super().__init__(cursor_highlight, sct=sct)
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
            rect.width,
            rect.height,
            current_cursor,
            left=rect.left,
            top=rect.top,
            enabled=cursor_highlight,
        )

    def grab(self) -> bytes:
        return self.prepare_frame(self._sct.grab(self._rect))

    def capture_rect(self) -> WindowRect:
        """The captured region's rect on the virtual screen."""
        return WindowRect(
            self._rect["left"],
            self._rect["top"],
            self._rect["width"],
            self._rect["height"],
        )

def ensure_dpi_aware() -> None:
    """Make the process per-monitor DPI aware on Windows.

    Process-start setup step: ``GetWindowRect`` reports logical pixels in a
    DPI-unaware process, while mss captures physical pixels; at any display
    scaling other than 100% window rects are then misaligned with the
    captured frames. Call once at process start, before any window-rect
    query (``list_windows``/``find_window``).
    """
    if sys.platform == "win32":
        with suppress(OSError):
            # PROCESS_PER_MONITOR_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(2)


def list_windows() -> list[tuple[str, WindowRect]]:
    """Enumerate all top-level windows as (title, bounding rect) pairs.

    Backs ``--list-windows`` so the user can pick a target for ``--window``.
    Platform-specific enumeration sits behind this boundary, same as
    ``find_window``, so callers never see platform differences.
    ``ensure_dpi_aware()`` must have run beforehand on Windows.
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
    ``ensure_dpi_aware()`` must have run beforehand on Windows.
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


def _parse_wmctrl_output(text: str) -> list[tuple[str, WindowRect]]:
    """Parse ``wmctrl -lG`` output into (title, rect) pairs.

    Each line is: window-id desktop-id x y width height hostname title;
    lines with fewer fields or non-numeric coordinates are skipped.
    """
    # wmctrl -lG prints: window-id desktop-id x y width height hostname title.
    windows: list[tuple[str, WindowRect]] = []
    for line in text.splitlines():
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
    return _parse_wmctrl_output(result.stdout)


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
