"""Audio module: the reserved audio abstraction boundary (per GLOSSARY).

Part of the package layout per ADR 0002. v1 recordings are video-only: no
real audio source is implemented. This module defines the data seam a future
audio input plugs into and ships ``NoopAudioSource`` so the recording session
can depend on the audio abstraction today. Adding real audio later means
implementing ``AudioSource`` and passing it to the session — the session
itself does not need restructuring.
"""
from abc import ABC, abstractmethod


class AudioSource(ABC):
    """A source of audio data for the recording pipeline.

    The reserved audio abstraction (GLOSSARY): the recording session pulls
    ``sample`` from it. v1 ships only the no-op stub, so recordings stay
    pure video; a real audio source plugs in without restructuring.
    """

    @abstractmethod
    def sample(self) -> bytes | None:
        """Return the next audio chunk, or ``None`` when nothing is ready."""
        ...


class NoopAudioSource(AudioSource):
    """No-op stub: v1 recordings are pure video, so this produces no audio."""

    def sample(self) -> bytes | None:
        return None
