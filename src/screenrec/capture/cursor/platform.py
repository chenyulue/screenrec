"""Cursor platform tracking: how each platform captures the cursor
(GLOSSARY: "cursor capture").

Cursor capture is platform-specific: on Linux, mss composites the cursor into
the grabbed frame itself (``with_cursor``), so only the cursor position is
needed here; on Windows, where mss cannot capture the cursor, the cursor
bitmap is captured via win32 (a port of upstream mss PR #272) and composited
by the annotator.

This module owns the whole platform matrix for cursor capture: the position
tracking (``current_cursor``) and the mss ``with_cursor`` capability
(``mss_composites_cursor``). The X11 display is encapsulated in ``X11Cursor``
with an explicit lifecycle and an injection seam, so the X11 tracking logic
is testable without a real display.
"""

import ctypes
import sys
from contextlib import suppress

from screenrec.capture.cursor.annotation import CursorImage

# Cursor bitmaps are captured onto a fixed-size surface on Windows.
CURSOR_SIZE = 32


def mss_composites_cursor() -> bool:
    """Whether mss composites the cursor into grabbed frames on this platform.

    True on Linux (mss's ``with_cursor`` feature); mss cannot composite the
    cursor elsewhere, so the annotator captures the cursor image separately.
    """
    return sys.platform == "linux"


def current_cursor() -> tuple[tuple[int, int], CursorImage | None] | None:
    """Return the cursor's screen position and captured image, or None.

    Two states are distinguished by the caller:
    - ``None``: no cursor available at all (no display, or tracking failed).
    - ``(position, None)``: the position is known but no image was captured
      (Linux: mss composites the image into the frame, so only the position is
      needed to place the highlight).
    """
    if sys.platform == "win32":
        return _cursor_windows()
    return _cursor_x11()


# Win32 structs for the Windows cursor-bitmap capture (used only on win32).
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]


class _CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("hCursor", ctypes.c_void_p),
        ("ptScreenPos", _POINT),
    ]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", ctypes.c_int32),
        ("xHotspot", ctypes.c_uint32),
        ("yHotspot", ctypes.c_uint32),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]


class X11Cursor:
    """Cursor position tracking over X11 via libX11 through ctypes.

    Encapsulates the open X11 display with an explicit lifecycle (lazy open,
    ``close``, reset) and an injection seam: pass a ``library``/``display`` to
    use an already-open (or fake) display, so the tracking logic is testable
    without a real X server. ``XQueryPointer`` needs an open display, and
    opening one per frame would be prohibitively slow; the capture loop runs on
    one thread, so the cached display sees no concurrent use.
    """

    def __init__(self, library: ctypes.CDLL | None = None, display: int = 0) -> None:
        # Injected libX11 (library + display) for tests; opened for real on
        # demand when not injected.
        self._library = library
        self._display = display

    def _ensure_open(self) -> ctypes.CDLL | None:
        """Open the display if needed; return the libX11 library, or None."""
        if self._library is not None:
            return self._library if self._display != 0 else None
        for library_name in ("libX11.so.6", "libX11.so"):
            try:
                library = ctypes.CDLL(library_name)
            except OSError:
                continue
            library.XOpenDisplay.restype = ctypes.c_void_p
            library.XOpenDisplay.argtypes = [ctypes.c_char_p]
            library.XQueryPointer.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_ulong),
            ]
            library.XQueryPointer.restype = ctypes.c_int
            library.XDefaultRootWindow.restype = ctypes.c_ulong
            library.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            display = library.XOpenDisplay(None)
            if display:
                self._library = library
                self._display = display
                return library
        return None

    def position(self) -> tuple[int, int] | None:
        """The cursor's screen position, or None when unavailable."""
        library = self._ensure_open()
        if library is None:
            return None
        display = self._display
        # XQueryPointer's window argument must be a valid window: query the root
        # window of the default screen. Passing 0 (NULL) makes the X server reject
        # the request with BadWindow.
        root_win = library.XDefaultRootWindow(display)
        if root_win == 0:
            return None
        root = ctypes.c_ulong(root_win)
        child = ctypes.c_ulong(0)
        root_x, root_y = ctypes.c_int(0), ctypes.c_int(0)
        win_x, win_y = ctypes.c_int(0), ctypes.c_int(0)
        mask = ctypes.c_ulong(0)
        found = library.XQueryPointer(
            display,
            root_win,
            ctypes.byref(root),
            ctypes.byref(child),
            ctypes.byref(root_x),
            ctypes.byref(root_y),
            ctypes.byref(win_x),
            ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        if not found:
            return None
        return (root_x.value, root_y.value)

    def close(self) -> None:
        """Close the display (if this instance opened it) and reset the cache."""
        if self._library is not None and self._display:
            close = getattr(self._library, "XCloseDisplay", None)
            if close is not None:
                with suppress(OSError, AttributeError):
                    close(self._display)
        self._library = None
        self._display = 0


# Module-level singleton: the X11 display is opened once and reused across
# frames (opening per frame would be prohibitively slow). The capture loop runs
# on one thread, so the cached display sees no concurrent use.
_X11_CURSOR = X11Cursor()


def _cursor_x11() -> tuple[tuple[int, int], CursorImage | None] | None:
    """Cursor screen position via X11 XQueryPointer (libX11 through ctypes)."""
    position = _X11_CURSOR.position()
    if position is None:
        return None
    return position, None


def _cursor_windows() -> tuple[tuple[int, int], CursorImage | None] | None:
    """Cursor screen position and bitmap via win32.

    The position comes from ``GetCursorPos`` (pywin32). The cursor bitmap is
    captured with the raw win32 API (a port of upstream mss PR #272):
    ``GetCursorInfo`` yields the cursor handle, ``DrawIcon`` renders it onto a
    compatible bitmap, ``GetDIBits`` reads the pixels back, and
    ``GetIconInfo`` provides the hotspot. pywin32's own ``GetCursorInfo`` does
    not expose a usable cursor handle, so the raw API is used for the image.
    """
    import win32gui

    x, y = win32gui.GetCursorPos()

    user32 = ctypes.windll.user32
    cursor_info = _CURSORINFO()
    cursor_info.cbSize = ctypes.sizeof(_CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(cursor_info)):
        return (x, y), None
    hcursor = cursor_info.hCursor
    if not hcursor:
        return (x, y), None  # no cursor image available; highlight only

    gdi32 = ctypes.windll.gdi32
    hdc = user32.GetDC(0)
    try:
        memdc = gdi32.CreateCompatibleDC(hdc)
        try:
            bitmap = gdi32.CreateCompatibleBitmap(hdc, CURSOR_SIZE, CURSOR_SIZE)
            gdi32.SelectObject(memdc, bitmap)
            user32.DrawIcon(memdc, 0, 0, hcursor)

            pixels = ctypes.create_string_buffer(CURSOR_SIZE * CURSOR_SIZE * 4)
            bmi = _BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = CURSOR_SIZE
            bmi.bmiHeader.biHeight = -CURSOR_SIZE  # top-down rows
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            if (
                gdi32.GetDIBits(
                    memdc, bitmap, 0, CURSOR_SIZE, pixels, ctypes.byref(bmi), 0
                )
                != CURSOR_SIZE
            ):
                return (x, y), None

            icon_info = _ICONINFO()
            if not user32.GetIconInfo(hcursor, ctypes.byref(icon_info)):
                return (x, y), None

            data = bytes(pixels)
            if not icon_info.hbmColor:
                # Monochrome cursor: DrawIcon leaves alpha at 0, so derive it
                # from the pixel: black is transparent, anything else opaque.
                corrected = bytearray(data)
                for i in range(3, len(corrected), 4):
                    corrected[i] = 0 if data[i - 3 : i] == b"\x00\x00\x00" else 255
                data = bytes(corrected)
            return (x, y), CursorImage(
                pixels=data,
                width=CURSOR_SIZE,
                height=CURSOR_SIZE,
                hotspot=(icon_info.xHotspot, icon_info.yHotspot),
            )
        finally:
            gdi32.DeleteDC(memdc)
    finally:
        user32.ReleaseDC(0, hdc)
