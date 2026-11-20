# Spec: screenrec CLI v1

Status: ready-for-agent

## Problem Statement

The user needs to record the screen as a video file on two different platforms: Windows (x86_64, the development machine) and Linux aarch64 (the deployment target). Existing Python screen-capture options either do not support the target platforms, capture screenshots but never produce video, or require per-platform custom code that drifts apart over time. mss provides fast, cross-platform raw pixel capture, but it outputs uncompressed frames only — there is no recording-session lifecycle, no encoding into a video file, no command-line experience, and no handling of platform-specific concerns like window enumeration. The user wants one tool that captures the screen and writes a usable video file, with identical behavior on both platforms.

## Solution
A command-line tool, `screenrec`, that records the screen to MP4 (H.264) on Windows x86_64 and Linux aarch64. It supports fullscreen capture, region capture, and window capture (with region-grab semantics, unified across platforms). The real mouse cursor is captured and drawn with a light-yellow highlight to draw attention to mouse movement, and this cursor highlight can be switched off. v1 is video-only, behind a reserved audio abstraction. Internally, a producer-consumer pipeline runs a capture thread that grabs raw frames from mss into a bounded queue while a writer thread feeds those frames over a pipe into an ffmpeg process provided by imageio-ffmpeg; a cursor annotation step draws the highlight onto each frame before encoding. An optional live preview window, off by default, can show the frames being recorded in real time — either alongside recording or in a preview-only mode that writes no file. The recording session lifecycle handles start, frame pacing, graceful stop, and fatal stop with partial-output retention. The tool ships as an installable Python package exposing a `screenrec` console command, and both platform paths are continuously verified on GitHub Actions (windows-latest with a real display, ubuntu-arm64 under Xvfb).
A command-line tool, `screenrec`, that records the screen to MP4 (H.264) on Windows x86_64 and Linux aarch64. It supports fullscreen capture, region capture, and window capture (with region-grab semantics, unified across platforms). v1 is video-only, behind a reserved audio abstraction. Internally, a producer-consumer pipeline runs a capture thread that grabs raw frames from mss into a bounded queue while a writer thread feeds those frames over a pipe into an ffmpeg process provided by imageio-ffmpeg. The recording session lifecycle handles start, frame pacing, graceful stop, and fatal stop with partial-output retention. The tool ships as an installable Python package exposing a `screenrec` console command, and both platform paths are continuously verified on GitHub Actions (windows-latest with a real display, ubuntu-arm64 under Xvfb).

## User Stories

1. As a Windows user, I want to record the entire screen with a single command, so that I can capture what is happening on my screen without any GUI configuration.
2. As a Windows user, I want to record only a rectangular region of the screen, so that I can focus on a specific area and keep the output file small.
3. As a Windows user, I want to record a specific window selected by a title substring, so that I can capture one application without the rest of the desktop.
4. As a Linux aarch64 user on an X11 display server, I want to run the same commands, so that I have one tool with identical behavior on both target platforms.
5. As a user, I want recordings to default to `./recordings/rec-YYYYMMDD-HHMMSS.mp4`, so that recordings never silently overwrite each other and are easy to locate.
6. As a user, I want to override the output directory and file name, so that I can organize recordings the way I prefer.
7. As a user, I want to stop a recording session with Ctrl-C or Enter, so that I can end recording at a natural moment and get a complete, finalized MP4.
8. As a user, I want a `--duration` option to record for a fixed length of time, so that I can capture time-boxed segments and script recordings unattended.
9. As a user, I want a `--fps` option to control the frame rate, so that I can trade smoothness against file size.
10. As a user, I want a sensible default frame rate of 30fps with no configuration, so that the tool works out of the box.
11. As a user, when my `--window` title substring matches several windows, I want the first match to be used with a warning, so that I get a recording without ambiguity.
12. As a user, when I ask to record a window that does not exist, I want a clear startup error and a non-zero exit code, so that I immediately know the recording did not start.
13. As a user, when the recorded window disappears mid-session, I want the session to stop with a clear error and the partial output retained, so that I do not lose what was already recorded.
14. As a user, when the encoder process dies mid-session, I want the session to stop with a clear error and a non-zero exit code, so that I know the recording failed rather than being silently truncated.
15. As a user, when the disk fills up mid-session, I want a fatal stop with a clear error and the partial output retained, so that I can recover what was written.
16. As a user, I want capture to pace itself with sleep rather than busy-waiting, so that the tool does not consume the CPU while waiting between frames.
17. As a developer, I want the CLI entry point to be the primary test seam, driven as a subprocess, so that the whole capture→encode→file pipeline is verified end-to-end exactly as users run it.
18. As a developer, I want a session API seam that accepts injected capture-source and encoder factories, so that mid-session failures can be tested deterministically on any OS.
19. As a maintainer, I want CI to run the full test suite on both windows-latest and ubuntu-arm64 (under Xvfb), so that both platform paths are continuously verified.
20. As a future maintainer, I want an audio abstraction interface defined but stubbed with a no-op, so that audio input can be added later without restructuring the recording session.

21. As a user, I want the recording to include my real mouse cursor with a light-yellow highlight around it, so that mouse movement is clearly visible and draws the viewer's attention.
22. As a user, I want to switch the cursor highlight off, so that I can produce a clean recording without cursor annotation when I do not need it.
23. As a user, when recording a region or window, I want the cursor highlight to appear only when the cursor is inside the captured area, so that the highlight stays relevant to what is being recorded.

24. As a user, I want a live preview window to show the frames being recorded, so that I can see exactly what is being captured while it happens.
25. As a user, I want the preview window to be optional and off by default, so that scripted and headless recordings never pop open an unwanted window.
26. As a user, I want to quit the recording by pressing a key in the preview window, so that I can stop at a natural moment without returning to the terminal.
27. As a user, I want a preview-only mode that shows the capture live without writing a file, so that I can check what would be recorded before committing to a full recording.

## Implementation Decisions

- **Package layout (ADR 0002):** The code is structured as an installable src-layout package split by responsibility into four modules: `capture` (the mss wrapper plus the platform-specific WindowSource abstraction), `encoder` (the ffmpeg raw-frame pipe via imageio-ffmpeg), `session` (the recording-session lifecycle: start, frame pacing, stop, failure policy), and `cli` (argument parsing and the `screenrec` console entry point).
- **Capture backend:** Raw BGRA frames are grabbed with mss. Fullscreen capture and region capture are native mss operations. The Linux target assumes an X11 display server (ADR 0001); Wayland is out of scope for v1.
- **Window capture semantics:** Region-grab semantics, unified across platforms. The window's bounding rectangle is resolved at session start; the recording captures the visible on-screen content within that rectangle, including any other window overlapping it. Capturing the window's own buffer (PrintWindow-style semantics) is out of scope for v1.
- **WindowSource abstraction:** Windows enumerates windows via pygetwindow; Linux enumerates windows via wmctrl (X11 EWMH/NetWM) invoked as a subprocess. Both platform implementations sit behind a common interface so the session layer never sees platform differences.
- **Window matching:** Windows are located by a title substring. When several windows match, the first match is taken and a warning is emitted. A non-existent window fails validation at startup with a clear error and non-zero exit.
- **Encoding pipeline:** Raw BGRA frames are written over a pipe to an ffmpeg process provided by imageio-ffmpeg. imageio-ffmpeg's bundled binary ships a Linux aarch64 wheel, so there is no system-ffmpeg dependency on the target. The output container is MP4 with H.264 video.
- **Threading model:** Producer-consumer with a bounded queue. A capture thread grabs frames into the queue; a writer thread drains the queue and feeds the ffmpeg pipe. The bounded queue absorbs encoding jitter and prevents unbounded memory growth.
- **Frame pacing:** Sleep-based pacing with no busy-wait. Default frame rate is 30fps; `--fps` accepts values from 1 to 60.
- **Recording-session control:** Graceful stop is triggered by the user (Ctrl-C or Enter). An optional `--duration` time-boxes a session and triggers graceful stop automatically when it elapses.
- **Output contract:** Default output is `./recordings/rec-YYYYMMDD-HHMMSS.mp4`; the output directory is auto-created when missing. Both the directory and the file name are overridable via flags.
- **Failure policy:** Mid-session errors (recorded window disappears, disk full, encoder process dies) cause a fatal stop: the session stops immediately, the partial output is retained and reported to the user, and the process exits with a non-zero code. Graceful stop, by contrast, finalizes the encoder normally and produces a complete MP4. Failures are never silently swallowed.
- **Audio abstraction:** v1 is video-only. An audio abstraction interface is defined with a no-op stub; no real audio source is implemented.
- **CLI capture selection:** Parameterized only — `--monitor N`, `--region x,y,w,h`, `--window <title substring>`. Interactive cursor-based region selection is out of scope for v1.
- **CI verification:** GitHub Actions matrix with windows-latest (real display) and ubuntu-arm64 running under Xvfb (a virtual X11 display server, since CI runners have no physical screen). The arm64 interpreter is provisioned with uv.
- **Python version:** The existing scaffold's `requires-python >=3.14` is kept; dependencies are managed with uv.

- **Cursor capture:** The recording includes the real mouse cursor image. On Linux (X11), mss's `with_cursor` composites the cursor into each grabbed frame. On Windows, mss cannot capture the cursor, so a ported win32 cursor capture (win32gui/win32ui via pywin32) composites the cursor icon bitmap into the frame, following the approach of upstream PR #272.
- **Cursor position tracking:** Cursor position is tracked per frame on both platforms to place the highlight — X11 XQueryPointer on Linux, GetCursorPos on Windows. The highlight is suppressed when the cursor is outside the captured area.
- **Cursor highlight:** A light-yellow highlight is drawn around the cursor position on each raw frame before encoding, using a cross-platform drawing layer (Pillow). This is an annotation layer applied after capture, independent of the capture mode.
- **Cursor toggle:** `--cursor-highlight` defaults to on; `--no-cursor-highlight` disables both cursor capture and the highlight, producing plain video with no cursor annotation.
- **New dependencies:** Pillow for the frame annotation/drawing layer (cross-platform, ships an aarch64 wheel); pywin32 for the Windows cursor capture (Windows-only).

- **Preview window:** An optional live preview window, following the approach of the reference project py-screen-grab, built with OpenCV (namedWindow/imshow/waitKey). During recording, each frame is displayed in the preview window in addition to being encoded; the window size follows the capture region.
- **Preview toggle:** `--preview` enables the preview window during recording and defaults to off, so scripted and headless recordings never open a window by default.
- **Preview-only mode:** `--preview-only` shows the capture live in the preview window without writing a video file.
- **Preview quit:** Pressing q in the preview window triggers graceful stop of the recording session, finalizing the MP4 the same as Ctrl-C.
- **New dependency:** opencv-python (full, not headless) for the preview window GUI; it ships an aarch64 wheel, so there is no system dependency on the target.
- **Preview display environment:** The preview window requires a display server — a real display on Windows, Xvfb on Linux CI.

## Testing Decisions

- **What makes a good test:** Tests verify external behavior only — process exit codes, the existence and validity of output files, and user-facing error messages. They never assert on implementation internals such as queue depth, thread structure, or internal state.
- **Primary seam — CLI entry point (subprocess):** The `screenrec` command is driven as a real subprocess. This seam covers the fullscreen, region, and window capture happy paths with `--duration`; output naming and directory behavior; `--fps` handling; startup validation errors (invalid region coordinates, no window match); graceful stop on duration expiry; and encoder failure injected by overriding `IMAGEIO_FFMPEG_EXE` with a broken binary (expect fatal stop, a clear error, and a non-zero exit code).
- **Narrow seam — session API:** The session module exposes a programmatic API that accepts injected capture-source and encoder factories. This seam deterministically covers the mid-session failure paths that cannot be reliably orchestrated through the CLI on two OSes: the recorded window disappearing mid-session, the encoder dying mid-session, API-driven graceful stop, and partial-output retention on fatal stop.
- **Display environment:** Tests that need a display server run under Xvfb on Linux CI (a virtual X11 display server) and against the real display on Windows CI.
- **Output validation:** A produced recording is asserted to be a valid, decodable MP4 (probed with ffprobe) — mere file existence is not sufficient.
- **Prior art:** The repository currently has no tests. This spec introduces the first test suite; the CLI subprocess seam and the session API seam are its foundation.

- **Cursor highlight tests:** The cursor feature is verified at the primary seam (CLI subprocess) on both CI platforms. A short recording with `--cursor-highlight` produces a valid MP4 that includes the cursor annotation, and `--no-cursor-highlight` produces a valid MP4 without cursor annotation. Cursor position tracking and highlight drawing are exercised against the real display on Windows and under Xvfb on Linux.

- **Preview tests:** The preview feature is verified at the primary seam (CLI subprocess) on both CI platforms. Recording with `--preview` under Xvfb produces a valid MP4 and the preview window path does not break the recording flow; `--preview-only` shows the preview without producing a file; the default no-preview path continues to pass. The q-to-quit interaction is exercised where a display is available.

## Out of Scope

- Wayland display server support (ADR 0001 defines X11 as the target).
- Audio recording — the audio abstraction is defined and stubbed only.
- Interactive cursor-based region selection.
- Capturing the window's own buffer (PrintWindow-style semantics); v1 uses region-grab semantics.
- Standalone binary packaging (PyInstaller and similar); v1 ships as a pip-installable package.
- macOS support.
- Live streaming or real-time broadcasting.
- Stitching multiple monitors into a single frame.
- Alternative video containers or codecs beyond the default MP4/H.264.

## Further Notes

- The known limitations of window capture (overlapping content is included in the recording; only EWMH-managed top-level windows are visible) must surface as warnings and documentation rather than silent behavior.

- The Windows cursor capture ports upstream PR #272, which is unmerged and stale, so custom cursor icons and multi-monitor cursor edge cases are handled best-effort and may need refinement as they are encountered.

- The preview feature follows the implementation approach of the reference project py-screen-grab (OpenCV namedWindow/imshow/waitKey, preview toggled by parameter, preview-only mode).
- This spec consolidates the grilling decisions Q1–Q16. The canonical vocabulary lives in `GLOSSARY.md`; the accepted architectural decisions live in `docs/adr/0001` (X11 display server) and `docs/adr/0002` (package layout).
- Implementation should proceed module by module — capture, then encoder, then session, then cli — adding tests at each seam as the module lands.
