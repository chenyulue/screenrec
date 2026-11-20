# 07: Live preview window during recording and preview-only mode (toggleable)

**What to build:** While recording, a live preview window shows the frames being recorded in real time, and the user can quit the session by pressing a key in the window; the preview can be switched on and off (off by default), and a preview-only mode shows the capture live without writing a file; behavior is consistent on Windows and Linux aarch64.

**Blocked by:** 02: Fullscreen recording end-to-end (the preview display is hooked into the frame flow of the core encoding pipeline, at the same insertion point as the cursor annotation)

**Status:** ready-for-agent

- [ ] During recording, a live preview window shows the capture frames in real time (OpenCV namedWindow/imshow, window size following the capture region), while the same frames are encoded to the video file
- [ ] Pressing q in the preview window triggers graceful stop of the recording session, finalizing the MP4 normally
- [ ] `--preview` toggles the preview window during recording and defaults to off; when off, no window is opened and recording proceeds normally
- [ ] `--preview-only` mode shows the capture live in the preview window without writing a video file
- [ ] Seam tests pass: under Xvfb, a short recording with `--preview` produces a valid MP4 and the preview path does not break the recording flow; `--preview-only` produces no file; the default no-preview path continues to pass
