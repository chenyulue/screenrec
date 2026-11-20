"""Session module: the recording session lifecycle boundary (per ADR 0002).

Owns the recording session lifecycle — start, frame pacing, stop, and the
failure policy — coordinating the capture and encoder modules without
owning either of them.
"""

from abc import ABC, abstractmethod


class RecordingSession(ABC):
    """The full lifecycle from starting a recording to producing the video file."""

    @abstractmethod
    def start(self) -> None:
        """Begin the recording session."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """End the recording session and finalize the output."""
        ...
