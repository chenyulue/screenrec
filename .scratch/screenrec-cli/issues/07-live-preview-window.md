# 07: Live preview window during recording and preview-only mode (toggleable)

**What to build:** While recording, a live preview window shows the frames being recorded in real time, and the user can quit the session by pressing a key in the window; the preview can be switched on and off (off by default), and a preview-only mode shows the capture live without writing a file; behavior is consistent on Windows and Linux aarch64.

**Blocked by:** 02: Fullscreen recording end-to-end (the preview display is hooked into the frame flow of the core encoding pipeline, at the same insertion point as the cursor annotation)

**Status:** resolved

- [x] During recording, a live preview window shows the capture frames in real time (OpenCV namedWindow/imshow, window size following the capture region), while the same frames are encoded to the video file
- [x] Pressing q in the preview window triggers graceful stop of the recording session, finalizing the MP4 normally
- [x] `--preview` toggles the preview window during recording and defaults to off; when off, no window is opened and recording proceeds normally
- [x] `--preview-only` mode shows the capture live in the preview window without writing a video file
- [x] Seam tests pass: under Xvfb, a short recording with `--preview` produces a valid MP4 and the preview path does not break the recording flow; `--preview-only` produces no file; the default no-preview path continues to pass

## Comments

Implemented via TDD at the CLI subprocess seam plus a narrow session seam for the q-to-quit logic.

- **preview** (new module, per ADR 0002): `Preview` ABC (show/quit_requested/close) with `OpenCvPreview` wrapping OpenCV namedWindow/imshow/waitKey; window size follows the capture region (resizeWindow). Each shown frame is the same raw BGRA frame the encoder receives, converted to BGR for display only. `close()` destroys only the preview window.
- **session**: `DefaultRecordingSession` takes an optional `preview`. The capture loop dispatches each frame to a bounded preview queue (non-blocking; frames dropped if the display falls behind, so capture never stalls). `run()` drives the display on the main thread — OpenCV's GUI functions must run on the main thread, so the display loop lives there rather than in the capture thread. q in the preview calls `request_stop()` → graceful stop/finalize, same as Ctrl-C. `stop()` closes the preview.
- **encoder**: `NoopFrameEncoder` discards frames and finalizes trivially, for preview-only mode.
- **cli**: `--preview` (BooleanOptionalAction, default off) and `--preview-only` (no file written). Preview-only skips output creation and uses the no-op encoder.
- **deps**: opencv-python (full) + numpy added; CI Linux step installs libgl1/libglib2.0-0 for the OpenCV GUI backend under Xvfb.
- **Tests**: `tests/test_preview.py` — parser toggles, a session unit test for q→graceful-stop (fake preview, no display needed), and seam tests: `--preview` records a valid MP4, `--preview-only` writes no file. Full suite 45 passed, 1 skipped (POSIX-only SIGINT test).
- Two-axis code review (Standards + Spec) passed; applied: `destroyWindow` (preview-only window) and ADR 0002 amended for the new preview module.
- Known limits: q-detection is frame-gated (waitKey runs inside show()); if capture stalls, q is delayed but Ctrl-C/Enter still stop the session. Frames are dropped when the display falls behind (best-effort real-time, never stalls capture).
