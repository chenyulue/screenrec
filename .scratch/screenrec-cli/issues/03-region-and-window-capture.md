# 03: Region capture and window capture

**What to build:** As a user, I can choose to record a rectangular region or a specific window (window capture uses region-grab semantics), and invalid input fails at startup with a clear error — the capture-selection layer on top of the core recording path.

**Blocked by:** 02: Fullscreen recording end-to-end

**Status:** ready-for-agent

- [ ] `--region x,y,w,h` records an arbitrary rectangular region of the screen
- [ ] `--window <title substring>` records a specific window; the WindowSource abstraction has a pygetwindow implementation on Windows and a wmctrl implementation on Linux, with the session layer unaware of platform differences
- [ ] Window capture uses region-grab semantics: the window's bounding rectangle is resolved at session start and the visible on-screen content within that rectangle is recorded; this limitation is documented
- [ ] Window matching locates windows by title substring; when several windows match, the first match is taken and a warning is emitted
- [ ] Startup validation rejects invalid region coordinates and non-existent windows with a clear error and a non-zero exit code
- [ ] Seam tests pass: region recording and window recording are exercised under Xvfb (a test-helper process opens a window), and outputs are asserted to be valid MP4 files
