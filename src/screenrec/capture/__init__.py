"""Capture module: the capture backend boundary (per ADR 0002).

Owns the mss wrapper and the platform-specific ``WindowSource`` abstraction
that the rest of the pipeline consumes frames from. Fullscreen, region, and
window capture sources will be implemented against this boundary.
"""

from abc import ABC, abstractmethod

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
