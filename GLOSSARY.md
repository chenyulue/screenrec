# screenrec

Cross-platform screen recording software: Python + mss, CLI form, developed on Windows (x86_64) and targeting Linux aarch64 on an X11 display server.

## Language

**Display server**:
The system component that manages screen output and the windowing environment. The Linux target for this project is X11; the capture stack does not support Wayland.
_Avoid_: display system, window system

**Capture backend**:
The underlying OS interface a capture library uses to read screen pixels. On Linux this project relies on the X11 backend.
_Avoid_: capture driver, screen grabber

**Fullscreen capture**:
Capturing the entire visible screen area of a monitor or virtual screen.
_Avoid_: whole-screen recording

**Region capture**:
Capturing an arbitrary rectangular area of the screen, specified by coordinates.
_Avoid_: area capture, rectangle capture

**Window capture**:
Capturing a specific window. In this project the v1 semantics are region capture over the window's bounding rectangle: what is recorded is the visible on-screen content within that rectangle (including any other window overlapping it), not the window's own buffer.
_Avoid_: window screenshot (ambiguous about which semantics), window recording

**Recording session**:
The full lifecycle from starting a recording to stopping it and producing the video file.
_Avoid_: recording process (confused with OS process), recording task

**Encoding pipeline**:
The path by which raw frames captured by mss are compressed into a video file.
_Avoid_: encoding flow, compression pipeline

**Audio abstraction**:
The reserved interface layer for future audio input. v1 is video-only; audio is not implemented.
_Avoid_: audio interface (ambiguous with hardware audio interface)

**Window matching**:
Locating the target window by a substring of its title. When several windows match, the first match is taken and a warning is emitted.
_Avoid_: window search, window lookup

**Graceful stop**:
The user actively ending a recording session (Ctrl-C or Enter). The encoding pipeline is finalized normally, producing a complete MP4.
_Avoid_: normal stop, normal termination

**Fatal stop**:
A recording session interrupted by an error (window closed, disk full, encoder process died). No normal finalization; the partial output is retained and a non-zero exit code is reported.
_Avoid_: crash stop, abnormal termination

**Partial output**:
The video file already written when a recording session ends by fatal stop. It is not finalized, but it is retained and reported to the user rather than silently discarded.
_Avoid_: half-finished file, incomplete file

**Cursor capture**:
Capturing the real mouse cursor image and compositing it into the grabbed frame, so that mouse movement is visible in the recording. Provided by the capture stack on each platform; Windows requires a platform-specific capture path since the base capture library cannot capture the cursor there.
_Avoid_: pointer capture, mouse capture

**Cursor position tracking**:
Querying the cursor's screen coordinates on each frame, used to place the cursor highlight.
_Avoid_: cursor polling, mouse tracking

**Cursor highlight**:
A light-yellow annotation drawn around the cursor position on the frame to draw attention to mouse movement. It is toggleable, and is suppressed when the cursor is outside the captured area.
_Avoid_: cursor glow, mouse ring

**Preview window**:
A live window that shows the capture frames in real time during a recording session. It can be shown alongside recording or in a preview-only mode that writes no file; it is toggleable and off by default.
_Avoid_: preview screen, live view
