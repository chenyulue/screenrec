# 06: Real cursor capture and light-yellow highlight (toggleable)

**What to build:** The recording shows the real mouse cursor with a light-yellow highlight drawn around it to draw attention to mouse movement; the cursor highlight can be switched off with a single flag; behavior is consistent on Windows and Linux aarch64.

**Blocked by:** 02: Fullscreen recording end-to-end (the cursor annotation step is injected into the frame flow of the core encoding pipeline)

**Status:** ready-for-agent

- [ ] The recording includes the real mouse cursor image: on Linux, mss `with_cursor` composites the cursor into each grabbed frame; on Windows, a ported win32 cursor capture (pywin32) composites the cursor icon bitmap into the frame
- [ ] A light-yellow highlight is drawn around the cursor position on each frame, guiding attention to mouse movement
- [ ] Cursor position is tracked per frame on both platforms (Linux X11 XQueryPointer, Windows GetCursorPos); the highlight is suppressed when the cursor is outside the captured area
- [ ] `--cursor-highlight` defaults to on; `--no-cursor-highlight` disables both cursor capture and the highlight, producing plain video with no cursor annotation
- [ ] Seam tests pass on both CI platforms: a short recording with the highlight on produces a valid MP4, and the toggle-off path produces a valid MP4 without cursor annotation
