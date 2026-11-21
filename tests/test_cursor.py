"""Unit tests for cursor annotation (ticket 06).

The annotator is exercised against a fake cursor provider, so the geometry
of the highlight and the cursor-image compositing are verified without a
display server or win32.
"""

import pytest

from screenrec.capture.cursor import (
    HIGHLIGHT_BGRA,
    HIGHLIGHT_RADIUS,
    CursorAnnotator,
    CursorImage,
)

FRAME_W, FRAME_H = 32, 24
BLACK = bytes((0, 0, 0, 255))


def _blank_frame() -> bytearray:
    return bytearray(BLACK * FRAME_W * FRAME_H)


def _pixel(frame: bytearray, x: int, y: int) -> bytes:
    i = (y * FRAME_W + x) * 4
    return bytes(frame[i : i + 4])


def _provider(position: tuple[int, int] | None, image: CursorImage | None = None):
    """A cursor provider returning a fixed (position, image) pair."""
    return lambda: None if position is None else (position, image)


def test_highlight_drawn_as_ring_around_cursor() -> None:
    frame = _blank_frame()
    CursorAnnotator(FRAME_W, FRAME_H, provider=_provider((10, 10))).annotate(frame)
    for dx in range(-HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS + 1):
        # Top edge of the ring, and a corner pixel.
        assert _pixel(frame, 10 + dx, 10 - HIGHLIGHT_RADIUS) == HIGHLIGHT_BGRA
    assert _pixel(frame, 10 - HIGHLIGHT_RADIUS, 10 - HIGHLIGHT_RADIUS) == HIGHLIGHT_BGRA
    # The cursor position itself and the ring's interior stay untouched.
    assert _pixel(frame, 10, 10) == BLACK
    assert _pixel(frame, 10, 10 - HIGHLIGHT_RADIUS + 1) == BLACK


@pytest.mark.parametrize(
    "position",
    [(-1, 10), (10, -1), (FRAME_W, 10), (10, FRAME_H), (-1, -1)],
)
def test_highlight_suppressed_when_cursor_outside_frame(
    position: tuple[int, int],
) -> None:
    frame = _blank_frame()
    CursorAnnotator(FRAME_W, FRAME_H, provider=_provider(position)).annotate(frame)
    assert frame == _blank_frame()


def test_region_offset_converts_screen_coordinates_to_frame_coordinates() -> None:
    frame = _blank_frame()
    annotator = CursorAnnotator(
        FRAME_W, FRAME_H, left=100, top=50, provider=_provider((110, 60))
    )
    annotator.annotate(frame)
    # Screen (110, 60) is frame (10, 10); the ring appears there.
    assert _pixel(frame, 10, 10 - HIGHLIGHT_RADIUS) == HIGHLIGHT_BGRA
    # A cursor at screen (50, 50) falls outside the region at frame (-50, 0).
    frame2 = _blank_frame()
    annotator2 = CursorAnnotator(
        FRAME_W, FRAME_H, left=100, top=50, provider=_provider((50, 50))
    )
    annotator2.annotate(frame2)
    assert frame2 == _blank_frame()


def test_disabled_annotator_leaves_frame_untouched() -> None:
    frame = _blank_frame()
    annotator = CursorAnnotator(
        FRAME_W, FRAME_H, enabled=False, provider=_provider((10, 10))
    )
    assert annotator.annotate(frame) is frame
    assert frame == _blank_frame()


def test_no_cursor_available_leaves_frame_untouched() -> None:
    frame = _blank_frame()
    CursorAnnotator(FRAME_W, FRAME_H, provider=_provider(None)).annotate(frame)
    assert frame == _blank_frame()


def test_cursor_image_composited_at_hotspot() -> None:
    # 4x4 fully-opaque red cursor with its hotspot at (2, 2).
    image = CursorImage(pixels=bytes((0, 0, 255, 255)) * 16, width=4, height=4, hotspot=(2, 2))
    frame = _blank_frame()
    CursorAnnotator(FRAME_W, FRAME_H, provider=_provider((10, 10), image)).annotate(frame)
    # Image top-left is hotspot-adjusted: (10 - 2, 10 - 2) = (8, 8).
    for y in range(4):
        for x in range(4):
            assert _pixel(frame, 8 + x, 8 + y) == bytes((0, 0, 255, 255))


def test_cursor_image_alpha_blends_with_frame() -> None:
    # 1x1 half-transparent red cursor over black: 255 * 128 / 255 = 128.
    image = CursorImage(pixels=bytes((0, 0, 255, 128)), width=1, height=1, hotspot=(0, 0))
    frame = _blank_frame()
    CursorAnnotator(FRAME_W, FRAME_H, provider=_provider((0, 0), image)).annotate(frame)
    assert _pixel(frame, 0, 0) == bytes((0, 0, 128, 255))


def test_cursor_image_clipped_at_frame_edges() -> None:
    # 2x2 opaque red cursor placed with only its top-left pixel inside.
    image = CursorImage(pixels=bytes((0, 0, 255, 255)) * 4, width=2, height=2, hotspot=(0, 0))
    frame = _blank_frame()
    CursorAnnotator(
        FRAME_W, FRAME_H, provider=_provider((FRAME_W - 1, FRAME_H - 1), image)
    ).annotate(frame)
    assert _pixel(frame, FRAME_W - 1, FRAME_H - 1) == bytes((0, 0, 255, 255))
    # Nothing leaked outside the frame (the next frame row/column stay black
    # apart from the highlight ring drawn around the cursor position).
    for y in range(FRAME_H):
        for x in range(FRAME_W):
            pixel = _pixel(frame, x, y)
            if pixel not in (BLACK, bytes((0, 0, 255, 255)), HIGHLIGHT_BGRA):
                raise AssertionError(f"unexpected pixel at {x},{y}: {pixel!r}")
