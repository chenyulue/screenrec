"""Cursor module: real cursor capture and highlight annotation (ticket 06).

Owns the platform-specific cursor tracking and the annotation step injected
into the frame flow: compositing the cursor image and drawing the light-yellow
highlight around the cursor position.

Cursor image capture is platform-specific (GLOSSARY: "cursor capture"): on
Linux, mss composites the cursor into the grabbed frame itself (``with_cursor``),
so only the cursor position is needed here; on Windows, where mss cannot
capture the cursor, the cursor bitmap is captured via win32 (a port of upstream
mss PR #272) and composited here.
"""

import ctypes
import sys
from collections.abc import Callable
from dataclasses import dataclass

# Light-yellow highlight (BGRA), drawn as a square ring around the cursor.
HIGHLIGHT_BGRA = bytes((150, 255, 255, 255))
HIGHLIGHT_RADIUS = 10

# Cursor bitmaps are captured onto a fixed-size surface on Windows.
CURSOR_SIZE = 32


@dataclass(frozen=True)
class CursorImage:
    """A captured cursor bitmap: BGRA pixels and its hotspot offset."""

    pixels: bytes
    width: int
    height: int
    hotspot: tuple[int, int]


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


def current_cursor() -> tuple[tuple[int, int], CursorImage | None] | None:
    """Return the cursor's screen position and captured image, or None.

    The image is None on Linux: mss composites the cursor into the grabbed
    frame itself, so only the position is needed to place the highlight.
    """
    if sys.platform == "win32":
        return _cursor_windows()
    return _cursor_x11()


# Cached libX11 handle and display: XQueryPointer needs an open display, and
# opening one per frame would be prohibitively slow. The capture loop runs on
# one thread, so the cached display sees no concurrent use.
_X11_DISPLAY: tuple[ctypes.CDLL, int] | None = None


def _x11_display() -> tuple[ctypes.CDLL, int] | None:
    global _X11_DISPLAY
    if _X11_DISPLAY is None:
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
            display = library.XOpenDisplay(None)
            if display:
                _X11_DISPLAY = (library, display)
                break
    return _X11_DISPLAY


def _cursor_x11() -> tuple[tuple[int, int], CursorImage | None] | None:
    """Cursor screen position via X11 XQueryPointer (libX11 through ctypes)."""
    x11 = _x11_display()
    if x11 is None:
        return None
    library, display = x11
    root = ctypes.c_ulong(0)
    child = ctypes.c_ulong(0)
    root_x, root_y = ctypes.c_int(0), ctypes.c_int(0)
    win_x, win_y = ctypes.c_int(0), ctypes.c_int(0)
    mask = ctypes.c_ulong(0)
    found = library.XQueryPointer(
        display,
        root,
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
    return (root_x.value, root_y.value), None


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
            if gdi32.GetDIBits(memdc, bitmap, 0, CURSOR_SIZE, pixels, ctypes.byref(bmi), 0) != CURSOR_SIZE:
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


class CursorAnnotator:
    """Annotates raw BGRA frames with the real cursor and a highlight.

    ``annotate`` is injected into the frame flow between capture and encoding:
    it composites the cursor image (Windows only; Linux relies on mss
    ``with_cursor``) and draws the light-yellow highlight around the cursor
    position. The highlight is suppressed when the cursor is outside the
    captured area, and ``enabled=False`` disables cursor annotation entirely.

    ``provider`` is the per-frame cursor tracker (GLOSSARY: "cursor position
    tracking"); tests inject a fake to exercise the annotation geometry.
    """

    def __init__(
        self,
        width: int,
        height: int,
        left: int = 0,
        top: int = 0,
        enabled: bool = True,
        provider: (
            Callable[[], tuple[tuple[int, int], CursorImage | None] | None]
        ) = current_cursor,
    ) -> None:
        self._width = width
        self._height = height
        self._left = left
        self._top = top
        self._enabled = enabled
        self._provider = provider

    def annotate(self, frame: bytearray) -> bytearray:
        """Composite the cursor and draw the highlight into one BGRA frame."""
        if not self._enabled:
            return frame
        tracked = self._provider()
        if tracked is None:
            return frame
        (screen_x, screen_y), image = tracked
        x = screen_x - self._left
        y = screen_y - self._top
        if not (0 <= x < self._width and 0 <= y < self._height):
            return frame  # cursor outside the captured area: highlight suppressed
        if image is not None:
            _composite_cursor(frame, self._width, self._height, x, y, image)
        _draw_highlight(frame, self._width, self._height, x, y)
        return frame


def _draw_highlight(frame: bytearray, width: int, height: int, x: int, y: int) -> None:
    """Draw the light-yellow square ring around the cursor, clipped to the frame."""
    x0, x1 = max(0, x - HIGHLIGHT_RADIUS), min(width - 1, x + HIGHLIGHT_RADIUS)
    y0, y1 = max(0, y - HIGHLIGHT_RADIUS), min(height - 1, y + HIGHLIGHT_RADIUS)
    for py in range(y0, y1 + 1):
        row = py * width * 4
        for px in range(x0, x1 + 1):
            if max(abs(px - x), abs(py - y)) == HIGHLIGHT_RADIUS:
                i = row + px * 4
                frame[i : i + 4] = HIGHLIGHT_BGRA


def _composite_cursor(
    frame: bytearray, width: int, height: int, x: int, y: int, image: CursorImage
) -> None:
    """Alpha-composite a cursor image into the frame with its hotspot at (x, y)."""
    left = x - image.hotspot[0]
    top = y - image.hotspot[1]
    pixels = image.pixels
    for cy in range(image.height):
        fy = top + cy
        if not (0 <= fy < height):
            continue
        src_row = cy * image.width * 4
        dst_row = fy * width * 4
        for cx in range(image.width):
            fx = left + cx
            if not (0 <= fx < width):
                continue
            src = src_row + cx * 4
            alpha = pixels[src + 3]
            if alpha == 0:
                continue
            dst = dst_row + fx * 4
            if alpha == 255:
                frame[dst : dst + 4] = pixels[src : src + 4]
            else:  # the frame is opaque: straight alpha blend over it
                for k in range(3):
                    frame[dst + k] = (
                        pixels[src + k] * alpha + frame[dst + k] * (255 - alpha)
                    ) // 255
                frame[dst + 3] = 255
