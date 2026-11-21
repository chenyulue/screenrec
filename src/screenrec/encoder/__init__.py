"""Encoder module: the raw-frame to video-file boundary (per ADR 0002).

Owns the encoding pipeline that compresses raw frames captured by the
capture module into a video file, via an ffmpeg raw-frame pipe.
"""
import subprocess
from abc import ABC, abstractmethod
from contextlib import suppress

from imageio_ffmpeg import get_ffmpeg_exe


class EncoderError(RuntimeError):
    """Raised when the ffmpeg encoding pipeline fails."""


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


class FfmpegFrameEncoder(FrameEncoder):
    """Feeds raw BGRA frames to an ffmpeg process over a pipe, writing MP4/H.264."""

    def __init__(self, width: int, height: int, fps: int, output: str) -> None:
        self._output = output
        cmd = [
            get_ffmpeg_exe(),
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def push(self, frame: bytes) -> None:
        if self._proc.stdin is None:
            raise EncoderError("ffmpeg stdin is closed")
        try:
            self._proc.stdin.write(frame)
        except OSError as exc:
            raise EncoderError(f"ffmpeg stopped accepting frames: {exc}") from exc

    def finalize(self) -> None:
        stderr = b""
        if self._proc.stdin is not None:
            with suppress(OSError):
                self._proc.stdin.close()
        code = self._proc.wait()
        if self._proc.stderr is not None:
            stderr = self._proc.stderr.read()
        if code != 0:
            detail = stderr.decode(errors="replace").strip()
            raise EncoderError(f"ffmpeg exited with code {code}: {detail}")


class NoopFrameEncoder(FrameEncoder):
    """A FrameEncoder that discards every frame and finalizes trivially.

    Used by preview-only mode, which shows the capture live without writing
    a video file (ticket 07).
    """

    def push(self, frame: bytes) -> None:
        """Discard the frame; nothing is written."""
        return

    def finalize(self) -> None:
        """No output to finalize."""
        return
