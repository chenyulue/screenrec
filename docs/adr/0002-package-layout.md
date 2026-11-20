# Package layout: src-layout with capture/encoder/session/cli modules

The project is structured as an installable package in src-layout, split by responsibility: `capture` (mss wrapper plus the platform-specific WindowSource abstraction), `encoder` (ffmpeg raw-frame pipe via imageio-ffmpeg), `session` (recording session lifecycle: start, frame pacing, stop, failure policy), and `cli` (argument parsing and the `screenrec` console entry point). A single-file script was rejected because the capture→encode producer-consumer pipeline, platform-specific window enumeration, and the test suite all need independently testable boundaries.

**Status**: accepted
