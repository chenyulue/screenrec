"""Unit tests for the X11 cursor tracker logic (cursor.platform.X11Cursor).

The X11 tracking is exercised with an injected fake libX11, so the logic
(root-window query, BadWindow guard, XQueryPointer result) is tested without
a real X server — the failure mode that was invisible when the display cache
was a bare module global with no injection hook.
"""

import ctypes
from typing import cast

from screenrec.capture.cursor.platform import X11Cursor


class _FakeX11:
    """Stands in for the libX11 ctypes library."""

    def __init__(self, root_win=1, found=True, position=(10, 20)) -> None:
        self._root_win = root_win
        self._found = found
        self._position = position
        self.xquery_calls = 0

    def XDefaultRootWindow(self, display: int) -> int:
        return self._root_win

    def XQueryPointer(
        self, display, win, root, child, root_x, root_y, win_x, win_y, mask
    ) -> int:
        self.xquery_calls += 1
        if self._found:
            root_x._obj.value = self._position[0]
            root_y._obj.value = self._position[1]
            return 1
        return 0


def _cursor(fake: _FakeX11, display: int = 123) -> X11Cursor:
    return X11Cursor(library=cast(ctypes.CDLL, fake), display=display)


def test_x11_returns_cursor_position() -> None:
    fake = _FakeX11(root_win=1, found=True, position=(10, 20))
    assert _cursor(fake).position() == (10, 20)


def test_x11_bad_window_guard_returns_none() -> None:
    """root_win == 0 (NULL window) is rejected before XQueryPointer is called."""
    fake = _FakeX11(root_win=0)
    assert _cursor(fake).position() is None
    assert fake.xquery_calls == 0


def test_x11_query_not_found_returns_none() -> None:
    fake = _FakeX11(root_win=1, found=False)
    assert _cursor(fake).position() is None


def test_x11_no_display_returns_none() -> None:
    """An injected library with display 0 reports no display."""
    fake = _FakeX11(root_win=1)
    assert X11Cursor(library=cast(ctypes.CDLL, fake), display=0).position() is None


def test_x11_close_resets_the_cache() -> None:
    cursor = _cursor(_FakeX11())
    cursor.position()
    cursor.close()
    assert cursor._library is None
    assert cursor._display == 0
