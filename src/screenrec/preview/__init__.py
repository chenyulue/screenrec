"""Preview module: the live preview window boundary (per ADR 0002, ticket 07).

Owns the display of capture frames during a recording session: showing each
frame in a named window and detecting the q-to-quit key. The session feeds
frames into this display at the same point it feeds the encoder, so the
preview shows exactly the frames being recorded.
"""

from abc import ABC, abstractmethod
from contextlib import suppress

import cv2
import numpy as np

from screenrec.capture import WindowRect

# Inset from a monitor's edge when placing the preview window on it.
PREVIEW_MARGIN = 20


def _monitor_overlaps(monitor: dict, rect: WindowRect) -> bool:
    """Whether a monitor's rect intersects the captured rect."""
    return not (
        monitor["left"] + monitor["width"] <= rect.left
        or rect.left + rect.width <= monitor["left"]
        or monitor["top"] + monitor["height"] <= rect.top
        or rect.top + rect.height <= monitor["top"]
    )


def resolve_placement(
    capture_rect: WindowRect, monitors: list[dict]
) -> tuple[int, int] | None:
    """Top-left of the first monitor the capture does not touch, or None.

    Layout policy for the preview window lives in the preview module; the
    capture backend only supplies the captured rect and the monitor table.
    """
    for candidate in monitors[1:]:  # index 0 is mss's virtual full-screen dummy
        if not _monitor_overlaps(candidate, capture_rect):
            return (
                candidate["left"] + PREVIEW_MARGIN,
                candidate["top"] + PREVIEW_MARGIN,
            )
    return None


class Preview(ABC):
    """A live display of capture frames, and the q-to-quit detection seam."""

    @abstractmethod
    def show(self, frame: bytes) -> None:
        """Display one raw BGRA frame in the preview window."""
        ...

    @abstractmethod
    def quit_requested(self) -> bool:
        """Whether the user pressed q in the preview window."""
        ...

    @abstractmethod
    def prepare(self) -> WindowRect | None:
        """Map the window and return its rect, or None when it cannot be located."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the preview window."""
        ...


class OpenCvPreview(Preview):
    """OpenCV namedWindow/imshow/waitKey implementation of the preview seam.

    The window size follows the capture region (``width`` x ``height``). Each
    shown frame is the same raw BGRA frame the encoder receives; it is
    converted to BGR for display only. ``prepare()`` maps the window and
    returns its rect, so the capture source can exclude it from the frames.
    """

    WINDOW_NAME = "screenrec preview"

    def __init__(
        self, width: int, height: int, position: tuple[int, int] | None = None
    ) -> None:
        self._width = width
        self._height = height
        self._quit = False
        self._rect: WindowRect | None = None
        # Requested window position, applied on the first show(): on Linux GTK
        # the window is not mapped until the first imshow, and the window
        # manager ignores move requests for unmapped windows.
        self._position = position
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.WINDOW_NAME, width, height)
        if position is not None:
            # Best-effort move at creation (effective on Windows); on Linux it
            # is re-applied once the window is mapped in show().
            cv2.moveWindow(self.WINDOW_NAME, position[0], position[1])

    def prepare(self) -> WindowRect | None:
        """Map the window on this thread and return its rect, or None.

        The window is not mapped until the first imshow (Linux GTK), and the
        window manager ignores move requests for unmapped windows — so
        mapping, moving and reading the rect all happen here, on the main
        thread, before the capture thread starts and can record the window
        inside its own frames.
        """
        cv2.imshow(
            self.WINDOW_NAME, np.zeros((self._height, self._width, 3), dtype=np.uint8)
        )
        if self._position is not None:
            # The window is mapped now, so the window manager honors the move
            # request: the preview lands on the intended monitor.
            cv2.moveWindow(self.WINDOW_NAME, self._position[0], self._position[1])
            self._position = None
        self._update_rect()
        return self._rect

    def show(self, frame: bytes) -> None:
        bgra = np.frombuffer(frame, dtype=np.uint8).reshape(
            self._height, self._width, 4
        )
        bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
        cv2.imshow(self.WINDOW_NAME, bgr)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            self._quit = True

    def quit_requested(self) -> bool:
        return self._quit

    def _update_rect(self) -> None:
        """Cache the window's rect on the virtual screen.

        getWindowImageRect is a GUI call, so it only ever runs on the main
        thread (from prepare()), never from the capture thread.
        """
        try:
            x, y, width, height = cv2.getWindowImageRect(self.WINDOW_NAME)
        except cv2.error:
            return
        if width > 0 and height > 0:
            self._rect = WindowRect(x, y, width, height)

    def close(self) -> None:
        # Tear down only this window, not every OpenCV window in the process.
        with suppress(cv2.error):
            cv2.destroyWindow(self.WINDOW_NAME)
