# 05: Audio abstraction stub

**What to build:** The audio abstraction interface is defined and wired into the recording session as a no-op stub — v1 stays video-only while a clean seam is left for future audio input, without restructuring the session.

**Blocked by:** 02: Fullscreen recording end-to-end

**Status:** resolved

- [x] The audio abstraction interface is defined, and the recording session accepts an audio-source dependency through it
- [x] v1 ships a no-op audio stub; no real audio source is implemented, and recording output remains pure video
- [x] A recording session with the stub wired in completes normally and passes its test
- [x] The interface is documented, and adding real audio later does not require restructuring the recording session

## Answer

Implemented as a data seam, not a lifecycle hook (per code review):

- **`src/screenrec/audio/__init__.py`** (new module, package layout per ADR 0002): defines the reserved **audio abstraction** (GLOSSARY) as the `AudioSource` ABC with a single data method `sample() -> bytes | None`, plus the v1 **no-op stub** `NoopAudioSource` (always returns `None`).
- **`src/screenrec/session/__init__.py`**: `DefaultRecordingSession` accepts `audio: AudioSource | None = None` (defaults to `NoopAudioSource()`) and the write loop **pulls `sample()` once per frame** next to `encoder.push(frame)` — the exact insertion point a real audio source will feed later. No session restructuring needed to add audio; no `close()` lifecycle was added (not asked for, and asymmetric with the other injected dependencies).
- **`tests/test_audio_stub.py`** (new): narrow-seam tests with fakes — stub produces no audio, session with the stub wired in completes normally and finalizes, session defaults to the stub, and the session actually pulls the data seam (counted pulls > 0).
- CLI unchanged: v1 output remains pure video.

Verification: `uv run pytest` 22 passed, 1 skipped (SIGINT test is POSIX-only); pyright 0 errors; isort clean.
