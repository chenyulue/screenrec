# 04: Recording session failure policy

**What to build:** When a recording session is interrupted mid-way (window disappears, encoder dies, disk fills), the session stops cleanly per the failure policy — partial output is retained, the error is reported clearly, and the process exits non-zero — the robustness guarantee of the recording session.

**Blocked by:** 02: Fullscreen recording end-to-end; 03: Region capture and window capture

**Status:** ready-for-agent

- [ ] A mid-session failure triggers fatal stop: the session stops immediately, the partial output is retained and reported to the user, and the process exits with a non-zero code
- [ ] The session module exposes a programmatic API that accepts injected capture-source and encoder factories (the narrow seam), with no platform assumptions baked into the test surface
- [ ] The narrow seam test deterministically covers the recorded window disappearing mid-session and the encoder dying mid-session — both trigger fatal stop and retain the partial output
- [ ] The primary seam test injects encoder failure by overriding the ffmpeg binary path with a broken executable: fatal stop, clear error, non-zero exit code
- [ ] No failure is silently swallowed; every failure path produces a clear user-facing error message
