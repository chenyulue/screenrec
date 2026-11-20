"""Capture module: the raw screen-pixel source boundary (per ADR 0002).

Owns the mss wrapper and the platform-specific ``WindowSource`` abstraction
that the rest of the pipeline consumes frames from. Fullscreen, region, and
window capture sources will be implemented against this boundary.
"""

from abc import ABC, abstractmethod


class WindowSource(ABC):
    """A source of raw screen frames for the recording pipeline."""

    @abstractmethod
    def grab(self) -> bytes:
        """Capture and return one raw frame."""
        ...
