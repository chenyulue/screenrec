# 04: Recording session failure policy

**What to build:** When a recording session is interrupted mid-way (window disappears, encoder dies, disk fills), the session stops cleanly per the failure policy — partial output is retained, the error is reported clearly, and the process exits non-zero — the robustness guarantee of the recording session.

**Blocked by:** 02: Fullscreen recording end-to-end; 03: Region capture and window capture

**Status:** resolved

- [x] A mid-session failure triggers fatal stop: the session stops immediately, the partial output is retained and reported to the user, and the process exits with a non-zero code
- [x] The session module exposes a programmatic API that accepts injected capture-source and encoder factories (the narrow seam), with no platform assumptions baked into the test surface
- [x] The narrow seam test deterministically covers the recorded window disappearing mid-session and the encoder dying mid-session — both trigger fatal stop and retain the partial output
- [x] The primary seam test injects encoder failure by overriding the ffmpeg binary path with a broken executable: fatal stop, clear error, non-zero exit code
- [x] No failure is silently swallowed; every failure path produces a clear user-facing error message

## Comments

The failure policy was already wired into `DefaultRecordingSession` from ticket 02 (`_fail()` sets `_error` and the stop event; `stop()` returns without finalizing on fatal stop). This ticket added the narrow-seam tests and two small fixes.

- Fixed a double-join bug in `stop()` (each thread was joined twice).
- CLI now prints the partial output path to stderr on fatal stop, so the user knows where the retained file is.
- `tests/test_failure_policy.py`: three narrow-seam tests inject fake `WindowSource` and `FrameEncoder` instances directly into `DefaultRecordingSession` — no mss, no ffmpeg, no platform assumptions. Covers window disappearing mid-session, encoder dying mid-session (both verify fatal stop + partial output retained), and a graceful-stop sanity check.
- Primary seam test (`test_broken_ffmpeg_binary_fails_with_clear_error` in `test_recording.py`) already covered the broken-ffmpeg CLI path; verified it still passes with the new stderr output.
- Full suite: 18 passed, 1 skipped (SIGINT on Windows). Pyright: 0 errors.
