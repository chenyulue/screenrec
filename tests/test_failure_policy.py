"""Narrow-seam tests for the recording session failure policy (ticket 04).

The seam under test is ``DefaultRecordingSession`` itself: a fake capture
source and a fake encoder are injected directly via the constructor, with no
platform assumptions (no mss, no ffmpeg, no subprocess). Each test drives a
deterministic mid-session failure and asserts the failure policy: fatal stop,
partial output retained, clear error.
"""

import threading
import time

from screenrec.capture import WindowRect, WindowSource
from screenrec.encoder import FrameEncoder
from screenrec.session import DefaultRecordingSession, SessionOutcome


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

    def __init__(self, fail_after: int | None = None, delay: float = 0.0) -> None:
        self._fail_after = fail_after
        self._delay = delay
        self._n = 0
        self.pushed: list[bytes] = []
        self.finalized = False
        self.aborted = False

    def push(self, frame: bytes) -> None:
        self._n += 1
        if self._fail_after is not None and self._n > self._fail_after:
            raise RuntimeError("encoder died mid-session")
        if self._delay:
            time.sleep(self._delay)
        self.pushed.append(frame)

    def finalize(self) -> None:
        self.finalized = True

    def abort(self) -> None:
        self.aborted = True


def _run_to_completion(
    session: DefaultRecordingSession, timeout: float = 10.0
) -> SessionOutcome:
    """Start and run the session in a thread, wait for it to finish."""
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"session did not stop within {timeout}s"
    return session.stop()


def test_window_disappearing_mid_session_triggers_fatal_stop() -> None:
    source = _FailingSource(grab_count=3)
    encoder = _RecordingEncoder()
    session = DefaultRecordingSession(source, encoder, fps=30)

    outcome = _run_to_completion(session)

    assert outcome.status == "fatal"
    assert "window disappeared" in str(outcome.error)
    # Partial output retained: frames pushed before the failure are kept,
    # but the encoder is aborted and not finalized (fatal stop, per GLOSSARY).
    assert encoder.pushed, "expected partial output (frames pushed before failure)"
    assert encoder.aborted, "fatal stop must abort the encoder"
    assert not encoder.finalized, "fatal stop must not finalize the encoder"


def test_encoder_dying_mid_session_triggers_fatal_stop() -> None:
    source = _FailingSource(grab_count=9999)  # source keeps producing
    encoder = _RecordingEncoder(fail_after=2)  # encoder dies after 2 pushes
    session = DefaultRecordingSession(source, encoder, fps=30)

    outcome = _run_to_completion(session)

    assert outcome.status == "fatal"
    assert "encoder died" in str(outcome.error)
    assert encoder.pushed, "expected partial output (frames pushed before failure)"
    assert encoder.aborted, "fatal stop must abort the encoder"
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
    outcome = session.run()  # timer fires after 0.1s → graceful stop

    assert outcome.status == "graceful"
    assert outcome.error is None
    assert encoder.finalized, "graceful stop must finalize the encoder"
    assert not encoder.aborted, "graceful stop must not abort the encoder"


def test_drain_failure_flips_stop_to_fatal() -> None:
    """A frame that fails during the tail drain makes the stop fatal: the
    encoder is aborted and never finalized (regression for the drain-leak,
    where a drain failure fell through to finalize)."""
    source = _FailingSource(grab_count=9999)
    # The writer's first push is slow, so stop lands while frames are still
    # queued; the drain then pushes the failing frame.
    encoder = _RecordingEncoder(fail_after=1, delay=0.3)
    session = DefaultRecordingSession(source, encoder, fps=30)

    run_thread = threading.Thread(target=session.run, daemon=True)
    run_thread.start()
    time.sleep(0.15)  # let the capture fill the queue while the writer is slow
    session.request_stop()
    run_thread.join(timeout=15.0)
    assert not run_thread.is_alive(), "session did not stop within 15s"

    outcome = session.stop()

    assert outcome.status == "fatal"
    assert "encoder died" in str(outcome.error)
    assert encoder.aborted, "drain failure must abort the encoder"
    assert not encoder.finalized, "drain failure must not finalize the encoder"
