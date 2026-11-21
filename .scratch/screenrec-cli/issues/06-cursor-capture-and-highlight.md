# 06: Real cursor capture and light-yellow highlight (toggleable)

**What to build:** The recording shows the real mouse cursor with a light-yellow highlight drawn around it to draw attention to mouse movement; the cursor highlight can be switched off with a single flag; behavior is consistent on Windows and Linux aarch64.

**Blocked by:** 02: Fullscreen recording end-to-end (the cursor annotation step is injected into the frame flow of the core encoding pipeline)

**Status:** resolved

- [x] The recording includes the real mouse cursor image: on Linux, mss `with_cursor` composites the cursor into each grabbed frame; on Windows, a ported win32 cursor capture (pywin32) composites the cursor icon bitmap into the frame
- [x] A light-yellow highlight is drawn around the cursor position on each frame, guiding attention to mouse movement
- [x] Cursor position is tracked per frame on both platforms (Linux X11 XQueryPointer, Windows GetCursorPos); the highlight is suppressed when the cursor is outside the captured area
- [x] `--cursor-highlight` defaults to on; `--no-cursor-highlight` disables both cursor capture and the highlight, producing plain video with no cursor annotation
- [x] Seam tests pass on both CI platforms: a short recording with the highlight on produces a valid MP4, and the toggle-off path produces a valid MP4 without cursor annotation

## Answer
Implemented the cursor annotation as a step injected into the grab→encode frame flow, owned by the capture boundary (ADR 0002, GLOSSARY "cursor capture"):

- **`src/screenrec/capture/cursor.py`** (new, under the capture module per ADR 0002): defines `CursorAnnotator`, the frame-annotation step. `annotate(frame)` composites the cursor image and draws the light-yellow square-ring highlight (`HIGHLIGHT_BGRA`) around the cursor position, suppressed when the cursor falls outside the captured rect. `CursorImage` carries the BGRA bitmap + hotspot. The per-frame cursor tracker is `current_cursor()`: on Linux, X11 `XQueryPointer` via ctypes (the image itself is composited by mss `with_cursor`, so the image is `None`); on Windows, `GetCursorPos` (pywin32) for the position and a port of upstream mss PR #272 for the bitmap (`GetCursorInfo` → `DrawIcon` → `GetDIBits` → `GetIconInfo` hotspot, with monochrome-alpha correction).
- **`src/screenrec/capture/__init__.py`**: `FullscreenSource` and `RegionSource` take `cursor_highlight: bool = True`; `_open_mss` opens mss with `with_cursor` on Linux only (mss warns/strips it elsewhere). Each source annotates its grabbed frame before enqueueing.
- **`src/screenrec/cli/main.py`**: `--cursor-highlight` / `--no-cursor-highlight` (`BooleanOptionalAction`, default on), passed to the chosen source.
- **`pyproject.toml`**: added `pywin32` (win32-only) for `GetCursorPos`.
- **Tests**: `tests/test_cursor.py` (12 unit tests of the annotator geometry/compositing against a fake cursor provider) and `tests/test_cursor_cli.py` (4 seam tests). The seam tests verify annotation *content*, not just validity: they decode the first frame of a toggle-on and a toggle-off recording of the same screen and assert the light-yellow highlight pixels appear only in the ON frame (comparison cancels screen content and encoding artifacts).

**Review notes (code-review, two axes):**
- Standards: no documented-standard breach. Duplicated-code and data-clump items were judgement calls — the only repeated shape is the one-line `CursorAnnotator(...)` construction, whose rect sources differ per source (extracting it would be a pure pass-through/Middle Man), so it was left inline. The `with_cursor` DeprecationWarning comment was verified against the mss source.
- Spec: the seam-test content gap (P1) was closed by the frame-comparison assertions above. A reviewer note citing "Pillow" as the spec's drawing layer was rejected — the spec names no Pillow dependency for the cursor highlight (raw BGRA drawing is used instead). The Windows image capture uses the raw win32 API rather than `win32ui`; this is a faithful port of PR #272 (which itself uses `ctypes.windll`), and pywin32 312's `GetCursorInfo` exposes no usable cursor handle, so the raw API is required for the bitmap; `GetCursorPos` still uses pywin32 as the ticket names.

Verification: `uv run pytest` 38 passed, 1 skipped (POSIX-only SIGINT test); pyright 0 errors; ruff clean on the changed files. CI runs the seam tests on windows-latest and ubuntu-arm64 (Xvfb).
