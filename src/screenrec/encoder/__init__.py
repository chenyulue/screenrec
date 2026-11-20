"""Encoder module: the raw-frame to video-file boundary (per ADR 0002).

Owns the encoding pipeline that compresses raw frames captured by the
capture module into a video file, via an ffmpeg raw-frame pipe.
"""

from abc import ABC, abstractmethod


class FrameEncoder(ABC):
    """Encodes raw captured frames into a video file."""

    @abstractmethod
    def push(self, frame: bytes) -> None:
        """Accept one raw frame for encoding."""
        ...

    @abstractmethod
    def finalize(self) -> None:
        """Finalize the output file so it is a complete, playable video."""
        ...
