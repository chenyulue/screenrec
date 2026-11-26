"""Cursor annotation: the pure geometry that composites the cursor image and
draws the light-yellow highlight around the cursor position.

This module is platform-agnostic and cheaply testable: the cursor tracker is
injected via ``provider``, so tests exercise the geometry without any display
or platform API. The real tracker (``current_cursor``) lives in
``cursor.platform`` and is wired in by the caller.
"""

from collections.abc import Callable
from dataclasses import dataclass

# Light-yellow highlight (BGRA), drawn as a square ring around the cursor.
HIGHLIGHT_BGRA = bytes((150, 255, 255, 255))
HIGHLIGHT_RADIUS = 10


@dataclass(frozen=True)
class CursorImage:
    """A captured cursor bitmap: BGRA pixels and its hotspot offset."""

    pixels: bytes
    width: int
    height: int
    hotspot: tuple[int, int]


class CursorAnnotator:
    """Annotates raw BGRA frames with the real cursor and a highlight.

    ``annotate`` is injected into the frame flow between capture and encoding:
    it composites the cursor image (Windows only; Linux relies on mss
    ``with_cursor``) and draws the light-yellow highlight around the cursor
    position. The highlight is suppressed when the cursor is outside the
    captured area, and ``enabled=False`` disables cursor annotation entirely.

    ``provider`` is the per-frame cursor tracker (GLOSSARY: "cursor position
    tracking"); it returns ``(screen_position, cursor_image)`` or ``None`` when
    no cursor is available. Two states are distinguished by ``annotate``:
    ``None`` means no cursor at all, ``(position, None)`` means the position is
    known but no image was captured (Linux: mss composites the image into the
    frame). The real tracker is wired in by the caller (the platform module's
    ``current_cursor``); tests inject a fake to exercise the geometry.
    """

    def __init__(
        self,
        width: int,
        height: int,
        provider: Callable[[], tuple[tuple[int, int], CursorImage | None] | None],
        left: int = 0,
        top: int = 0,
        enabled: bool = True,
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
