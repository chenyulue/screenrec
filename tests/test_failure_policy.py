"""Narrow-seam tests for the recording session failure policy (ticket 04).

The seam under test is ``DefaultRecordingSession`` itself: a fake capture
source and a fake encoder are injected directly via the constructor, with no
platform assumptions (no mss, no ffmpeg, no subprocess). Each test drives a
deterministic mid-session failure and asserts the failure policy: fatal stop,
partial output retained, clear error.
"""

import threading

from screenrec.capture import WindowRect, WindowSource
from screenrec.encoder import FrameEncoder
from screenrec.session import DefaultRecordingSession


class _FailingSource(WindowSource):
    """Returns ``grab_count`` frames then raises — simulates a window disappearing."""

    def __init__(self, grab_count: int) -> None:
        self._grab_count = grab_count
        self._n = 0

    def grab(self) -> bytes:
        self._n += 1
        if self._n > self._grab_count:
            raise RuntimeError("window disappeared mid-session")
        return b"\x00" * 16

    def capture_rect(self) -> WindowRect:
        return WindowRect(0, 0, 4, 4)

    def monitors(self) -> list[dict]:
        return []


class _RecordingEncoder(FrameEncoder):
    """Records pushed frames; optionally raises after ``fail_after`` pushes."""

    def __init__(self, fail_after: int | None = None) -> None:
        self._fail_after = fail_after
        self._n = 0
        self.pushed: list[bytes] = []
        self.finalized = False

    def push(self, frame: bytes) -> None:
        self._n += 1
        if self._fail_after is not None and self._n > self._fail_after:
            raise RuntimeError("encoder died mid-session")
        self.pushed.append(frame)

    def finalize(self) -> None:
        self.finalized = True


def _run_to_completion(session: DefaultRecordingSession, timeout: float = 10.0) -> None:
    """Start and run the session in a thread, wait for it to finish."""
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"session did not stop within {timeout}s"


def test_window_disappearing_mid_session_triggers_fatal_stop() -> None:
    source = _FailingSource(grab_count=3)
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(source, encoder, fps=30)

    _run_to_completion(session)

    assert session.error is not None
    assert "window disappeared" in str(session.error)
    # Partial output retained: frames pushed before the failure are kept,
    # but the encoder is not finalized (fatal stop, per GLOSSARY).
    assert encoder.pushed, "expected partial output (frames pushed before failure)"
    assert not encoder.finalized, "fatal stop must not finalize the encoder"


def test_encoder_dying_mid_session_triggers_fatal_stop() -> None:
    source = _FailingSource(grab_count=9999)  # source keeps producing
    encoder = _RecordingEncoder(fail_after=2)  # encoder dies after 2 pushes
    session = DefaultRecordingSession(source, encoder, fps=30)

    _run_to_completion(session)

    assert session.error is not None
    assert "encoder died" in str(session.error)
    assert encoder.pushed, "expected partial output (frames pushed before failure)"
    assert not encoder.finalized, "fatal stop must not finalize the encoder"


def test_graceful_stop_finalizes_without_error() -> None:
    """Sanity check: a normal stop with no failure finalizes cleanly."""

    class _NeverFails(WindowSource):
        def grab(self) -> bytes:
            return b"\x00" * 16

        def capture_rect(self) -> WindowRect:
            return WindowRect(0, 0, 4, 4)

        def monitors(self) -> list[dict]:
            return []

    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(_NeverFails(), encoder, fps=30, duration=0.1)

    session.start()
    session.run()  # timer fires after 0.1s → graceful stop

    assert session.error is None
    assert encoder.finalized, "graceful stop must finalize the encoder"
