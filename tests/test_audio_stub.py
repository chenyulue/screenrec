"""Narrow-seam tests for the reserved audio abstraction (ticket 05).

The seam under test is the ``AudioSource`` interface and its wiring into
``DefaultRecordingSession``: v1 ships a no-op stub, the session accepts an
audio abstraction dependency through it and pulls its data seam, and a
session wired with the stub completes normally producing pure video (no real
audio source exists).
"""
import threading

from screenrec.audio import AudioSource, NoopAudioSource
from screenrec.capture import WindowRect, WindowSource
from screenrec.encoder import FrameEncoder
from screenrec.session import DefaultRecordingSession


class _NeverFailsSource(WindowSource):
    """Capture source that produces frames indefinitely."""

    def grab(self) -> bytes:
        return b"\x00" * 16

    def capture_rect(self) -> WindowRect:
        return WindowRect(0, 0, 4, 4)

    def monitors(self) -> list[dict]:
        return []


class _RecordingEncoder(FrameEncoder):
    """Records pushed frames and whether finalize ran."""

    def __init__(self) -> None:
        self.pushed: list[bytes] = []
        self.finalized = False

    def push(self, frame: bytes) -> None:
        self.pushed.append(frame)

    def finalize(self) -> None:
        self.finalized = True


class _CountingAudio(AudioSource):
    """Fake AudioSource that counts pulls, to assert the session's data seam."""

    def __init__(self) -> None:
        self.samples_pulled = 0

    def sample(self) -> bytes | None:
        self.samples_pulled += 1
        return None


def _run_session(session: DefaultRecordingSession, timeout: float = 10.0) -> None:
    """Start and run the session in a thread, wait for it to finish."""
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"session did not stop within {timeout}s"


def test_noop_stub_produces_no_audio() -> None:
    assert NoopAudioSource().sample() is None


def test_session_with_stub_wired_in_completes_normally() -> None:
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(
        _NeverFailsSource(),
        encoder,
        fps=30,
        duration=0.1,
        audio=NoopAudioSource(),
    )
    _run_session(session)
    assert session.error is None
    assert encoder.pushed, "expected frames to be recorded"
    assert encoder.finalized, "graceful stop must finalize the encoder"


def test_session_defaults_to_noop_audio_stub() -> None:
    """v1 callers that pass no audio source still get the no-op stub wired in."""
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(_NeverFailsSource(), encoder, fps=30, duration=0.1)
    _run_session(session)
    assert session.error is None
    assert encoder.finalized


def test_session_pulls_audio_samples_during_recording() -> None:
    """The session's write loop pulls the audio abstraction's data seam."""
    audio = _CountingAudio()
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(
        _NeverFailsSource(), encoder, fps=30, duration=0.1, audio=audio
    )
    session.start()
    session.run()
    assert session.error is None
    assert audio.samples_pulled > 0, "session must pull the audio data seam"
