# 02: Fullscreen recording end-to-end

**What to build:** As a user, I can record the entire screen for a chosen duration from the command line and get a complete, valid MP4 file — the core recording path, cut end-to-end from the capture backend through the encoding pipeline to the output contract.

**Blocked by:** 01: Package skeleton, console entry point, and CI matrix baseline

**Status:** ready-for-agent

- [ ] `--monitor N --duration S` records the fullscreen; when the duration elapses the recording session stops gracefully and the encoder finalizes normally
- [ ] Manual Ctrl-C or Enter also triggers graceful stop and produces a complete MP4
- [ ] The capture thread feeds raw frames into the encoding pipeline via a producer-consumer bounded queue, so encoding jitter does not block capture
- [ ] Frame pacing uses sleep (no busy-wait), default frame rate is 30fps, and `--fps` accepts 1–60
- [ ] Output defaults to `./recordings/rec-YYYYMMDD-HHMMSS.mp4`; the directory is auto-created when missing, and the directory and file name are overridable via arguments
- [ ] The primary seam test passes: the CLI command, driven as a subprocess under Xvfb, records for a fixed duration, and ffprobe verifies the output is a valid, decodable MP4
