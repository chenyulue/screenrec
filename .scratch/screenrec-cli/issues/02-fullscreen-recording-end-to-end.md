# 02: Fullscreen recording end-to-end

**What to build:** As a user, I can record the entire screen for a chosen duration from the command line and get a complete, valid MP4 file — the core recording path, cut end-to-end from the capture backend through the encoding pipeline to the output contract.

**Blocked by:** 01: Package skeleton, console entry point, and CI matrix baseline

**Status:** resolved

- [x] `--monitor N --duration S` records the fullscreen; when the duration elapses the recording session stops gracefully and the encoder finalizes normally
- [x] Manual Ctrl-C or Enter also triggers graceful stop and produces a complete MP4
- [x] The capture thread feeds raw frames into the encoding pipeline via a producer-consumer bounded queue, so encoding jitter does not block capture
- [x] Frame pacing uses sleep (no busy-wait), default frame rate is 30fps, and `--fps` accepts 1–60
- [x] Output defaults to `./recordings/rec-YYYYMMDD-HHMMSS.mp4`; the directory is auto-created when missing, and the directory and file name are overridable via arguments
- [x] The primary seam test passes: the CLI command, driven as a subprocess under Xvfb, records for a fixed duration, and ffprobe verifies the output is a valid, decodable MP4

## Comments

Implemented via TDD at the CLI subprocess seam: `tests/test_recording.py` drove the module-by-module implementation (capture → encoder → session → cli, per spec).

- **capture**: `FullscreenSource(WindowSource)` wraps mss, `--monitor N` selects `mss.monitors[N]`, `grab()` returns raw BGRA bytes (`.width`/`.height` exposed for the encoder pipe). Out-of-range monitor → clear error, exit 1.
- **encoder**: `FfmpegFrameEncoder(FrameEncoder)` pipes raw BGRA frames into the imageio-ffmpeg binary (`-pix_fmt bgra`, `libx264`, `yuv420p` → MP4). New dependency `imageio-ffmpeg` per ADR 0002; honors `IMAGEIO_FFMPEG_EXE` for failure injection. Failures raise `EncoderError`.
- **session**: `DefaultRecordingSession` runs a capture producer → bounded queue (size 2) → writer consumer; sleep-based pacing with resync (no busy-wait); duration timer, Ctrl-C, and Enter all funnel through `request_stop()`, and `run()` performs the graceful stop on the main thread so finalization always completes before process exit. Fatal stop (any recorded error) skips normal finalization and retains the partial output unfinalized, per GLOSSARY. Enqueue is interruptible so a full queue at stop time cannot deadlock capture against the exiting writer.
- **cli**: `--monitor`, `--duration`, `--fps` (argparse `choices=range(1,61)`), `--output`; default `./recordings/rec-YYYYMMDD-HHMMSS.mp4` with auto-created directory; success prints the output path; failures exit 1 with a clear stderr message.
- Two-axis code review (Standards + Spec) passed; findings applied: fatal-stop now skips finalization (glossary), capture-enqueue interruptibility (stop deadlock), test helper extraction, `--monitor 1` on the happy path, docstring vocabulary.
- Local: full suite 9 passed, 1 skipped (SIGINT test is POSIX-only; runs under Xvfb on Linux CI). Live check: 2s @ 20fps → 38-frame 2560x1600 H.264 MP4, ffprobe-verified.
