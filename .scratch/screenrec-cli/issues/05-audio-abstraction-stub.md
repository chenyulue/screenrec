# 05: Audio abstraction stub

**What to build:** The audio abstraction interface is defined and wired into the recording session as a no-op stub — v1 stays video-only while a clean seam is left for future audio input, without restructuring the session.

**Blocked by:** 02: Fullscreen recording end-to-end

**Status:** ready-for-agent

- [ ] The audio abstraction interface is defined, and the recording session accepts an audio-source dependency through it
- [ ] v1 ships a no-op audio stub; no real audio source is implemented, and recording output remains pure video
- [ ] A recording session with the stub wired in completes normally and passes its test
- [ ] The interface is documented, and adding real audio later does not require restructuring the recording session
