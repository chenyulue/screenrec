"""Session module: the recording session lifecycle boundary (per ADR 0002).

Owns the recording session lifecycle — start, frame pacing, stop, and the
failure policy — coordinating the capture and encoder modules without
owning either of them.
"""

import queue
import threading
import time
from abc import ABC, abstractmethod

from screenrec.capture import WindowSource
from screenrec.encoder import FrameEncoder


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


class DefaultRecordingSession(RecordingSession):
    """Producer-consumer recording: a capture thread feeds a bounded queue
    that a writer thread drains into the encoder, so encoding jitter never
    blocks capture beyond the queue depth."""

    QUEUE_SIZE = 2

    def __init__(
        self,
        source: WindowSource,
        encoder: FrameEncoder,
        fps: int,
        duration: float | None = None,
    ) -> None:
        self._source = source
        self._encoder = encoder
        self._fps = fps
        self._duration = duration
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=self.QUEUE_SIZE)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._error: Exception | None = None
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._writer_thread = threading.Thread(target=self._write_loop, daemon=True)
        self._timer: threading.Timer | None = None
        self._started = False

    @property
    def error(self) -> Exception | None:
        """The fatal error that stopped the session, if any."""
        return self._error

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("session is already started")
            self._started = True
        self._capture_thread.start()
        self._writer_thread.start()
        if self._duration is not None:
            self._timer = threading.Timer(self._duration, self.request_stop)
            self._timer.daemon = True
            self._timer.start()

    def request_stop(self) -> None:
        """Ask the running session to stop; run() performs the graceful stop."""
        self._stop_event.set()

    def run(self) -> None:
        """Block until stop is requested, then perform the graceful stop."""
        if not self._started:
            self.start()
        self._stop_event.wait()
        self.stop()
    def stop(self) -> None:
        """Stop gracefully: halt capture, drain queued frames, finalize output."""
        with self._lock:
            if not self._started:
                return
            self._started = False
            self._stop_event.set()
        if self._timer is not None:
            self._timer.cancel()
        self._capture_thread.join()
        self._writer_thread.join()
        self._capture_thread.join()
        self._writer_thread.join()
        if self._error is not None:
            # Fatal stop: the partial output is retained unfinalized (GLOSSARY).
            return
        # Graceful stop: drain whatever is still queued so the tail of the
        # recording is not lost, then finalize normally.
        while not self._queue.empty():
            try:
                self._encoder.push(self._queue.get_nowait())
            except Exception as exc:
                self._fail(exc)
        try:
            self._encoder.finalize()
        except Exception as exc:
            self._fail(exc)

    def _fail(self, exc: Exception) -> None:
        if self._error is None:
            self._error = exc
        self._stop_event.set()

    def _capture_loop(self) -> None:
        interval = 1.0 / self._fps
        next_tick = time.monotonic()
        try:
            while not self._stop_event.is_set():
                frame = self._source.grab()
                if self._enqueue(frame) or self._stop_event.is_set():
                    break
                next_tick += interval
                delay = next_tick - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.monotonic()  # fell behind: resync, no busy-wait
        except Exception as exc:
            self._fail(exc)

    def _enqueue(self, frame: bytes) -> bool:
        """Enqueue a frame, blocking while the writer falls behind.

        Interruptible by stop: without this, a full queue at stop time would
        deadlock capture against a writer that has already exited.
        """
        while not self._stop_event.is_set():
            try:
                self._queue.put(frame, timeout=0.1)
                return False
            except queue.Full:
                continue
        return True  # stop was requested while waiting; tail frame dropped

    def _write_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    frame = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._encoder.push(frame)
        except Exception as exc:
            self._fail(exc)
