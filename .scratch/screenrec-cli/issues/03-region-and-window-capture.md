# 03: Region capture and window capture

**What to build:** As a user, I can choose to record a rectangular region or a specific window (window capture uses region-grab semantics), and invalid input fails at startup with a clear error — the capture-selection layer on top of the core recording path.

**Blocked by:** 02: Fullscreen recording end-to-end

**Status:** resolved

- [x] `--region x,y,w,h` records an arbitrary rectangular region of the screen
- [x] `--window <title substring>` records a specific window; the WindowSource abstraction has a pygetwindow implementation on Windows and a wmctrl implementation on Linux, with the session layer unaware of platform differences
- [x] Window capture uses region-grab semantics: the window's bounding rectangle is resolved at session start and the visible on-screen content within that rectangle is recorded; this limitation is documented
- [x] Window matching locates windows by title substring; when several windows match, the first match is taken and a warning is emitted
- [x] Startup validation rejects invalid region coordinates and non-existent windows with a clear error and a non-zero exit code
- [x] Seam tests pass: region recording and window recording are exercised under Xvfb (a test-helper process opens a window), and outputs are asserted to be valid MP4 files

## Comments

Implemented via TDD at the CLI subprocess seam: `tests/test_region_window.py` drove the implementation (capture → cli).

- **capture**: `RegionSource(WindowSource)` wraps mss region grabs; startup validation rejects non-positive size and rects outside the virtual screen with clear errors. `find_window(title_substring)` is the platform boundary: pygetwindow on Windows, `wmctrl -lG` (X11 EWMH) on Linux, both returning a `WindowMatch(rect, warning)`; the first match wins and a warning is returned on multiple matches. Window capture is region-grab semantics: the CLI resolves the rect at startup and feeds a `RegionSource` — the session layer never sees platform differences. New Windows-only dependency `pygetwindow` (`sys_platform == 'win32'` marker); wmctrl is a Linux system command invoked as a subprocess.
- **cli**: `--region x,y,w,h` and `--window TITLE` join `--monitor` in a mutually exclusive capture-selection group; `--region` uses an argparse type parser (format errors exit 2), source-level validation exits 1. Window warnings print to stderr.
- **tests**: `tests/open_window.py` is an X11 ctypes test helper that maps windows titled `screenrec-test-window-N`, registers them in `_NET_CLIENT_LIST` (no window manager runs under plain Xvfb, so nothing else maintains the EWMH client list), prints READY, and stays alive; the Windows path uses an inline PowerShell WinForms helper. Tests cover region happy path, region format/coordinate validation, non-existent window, window happy path, and the multiple-match warning; outputs asserted with ffprobe.
- **docs**: README documents region capture and window capture with its region-grab limitations (overlapping content included, EWMH-managed windows only on Linux).
- Local (Windows): full suite 15 passed, 1 skipped (SIGINT test is POSIX-only). The Xvfb/wmctrl path is exercised on Linux CI.

- **review (two-axis)**: Spec axis caught a P0 — `wmctrl -lG` prints `window-id desktop-id x y w h hostname title` (verified against the wmctrl 1.07 source, `list_windows` in `main.c`); the initial title-before-geometry parse was corrected to split all fields and take the title from the tail. Standards axis findings applied: `_first_match` extracted to remove the duplicated no-match/warning shape; `RegionSource` now takes a `WindowRect` (removes the four-int clump); test renamed to `test_window_capture_...` per GLOSSARY's avoid-list; `_xfunc` renamed `_configure_x11`. Spec P2 (window disappearing mid-session) deferred to ticket 04, which owns the failure policy.

- **`--list-windows`**: users did not know window titles beforehand, so they need a way to enumerate them before picking a `--window` target. The capture boundary gains `list_windows()`, returning (title, rect) pairs for all top-level windows; the platform enumeration is refactored into `_list_windows_windows`/`_list_windows_x11`, now shared with `find_window` (no duplicated wmctrl/pygetwindow parsing). The CLI's `--list-windows` prints each title with its bounding rect (tab-separated) and exits without recording; errors (missing wmctrl on Linux) surface like other startup failures. Tests: parser flag test plus a seam test asserting a window opened by the test helper appears in the output.

- **DPI-aware window rects (Windows)**: on scaled displays the window recording region was misaligned with the actual window. `find_window`/`list_windows` ran while the process was still DPI-unaware, so `GetWindowRect` returned logical pixels while mss captures physical pixels (verified at 150% scaling: logical 208,208,316,239 vs physical 312,312,474,359). Fix: `_ensure_dpi_aware()` (`SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)`) runs before enumeration, matching mss's own behavior. Also fixed a latent encoder bug exposed by odd physical dimensions at non-100% scaling: libx264 requires even sides, so `FfmpegFrameEncoder` now pads frames via `-vf pad=ceil(iw/2)*2:ceil(ih/2)*2` (no-op for even sizes). Tests: `test_window_enumeration_ensures_dpi_aware` (monkeypatched wiring check) and `test_encoder_accepts_odd_frame_dimensions`; alignment verified end-to-end against an mss ground-truth grab.
