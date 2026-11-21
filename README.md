# screenrec

Cross-platform screen recording software: a Python + mss CLI for recording
the screen to video files. Developed on Windows (x86_64) and targeting
Linux aarch64 on an X11 display server.

## Install

```sh
uv sync
```

## Usage

```sh
screenrec --help
screenrec --version
```

Common options:

- `--duration S` — record for S seconds, then stop gracefully and finalize the MP4.
- `--fps F` — frame rate, 1–60 (default: 30).
- `--output PATH` — output MP4 path (default: `./recordings/rec-YYYYMMDD-HHMMSS.mp4`; the directory is created if missing).

A recording runs until `--duration` elapses, or until you stop it with **Ctrl-C** or **Enter** — both trigger a graceful stop that finalizes the MP4 normally.

### Fullscreen capture

```sh
screenrec --monitor 1 --duration 30
```

Records the entire visible screen of monitor `N` (default: 1). This is the default capture mode when no `--region` or `--window` is given. An out-of-range monitor number fails at startup with a clear error and a non-zero exit code.

### Region capture

```sh
screenrec --region x,y,w,h --duration 30
```

Records the rectangular region of the screen at `(x, y)` with size `w` by `h`.
Invalid coordinates (non-positive size, or a rect outside the screen) fail at
startup with a clear error and a non-zero exit code.

### Window capture

```sh
screenrec --window "terminal" --duration 30
```

Records the first window whose title contains the given substring; when several
windows match, the first match is used and a warning is printed.

Window capture uses **region-grab semantics**: the window's bounding rectangle
is resolved at session start and the visible on-screen content within that
rectangle is recorded — including any other window overlapping it. The
window's own buffer (PrintWindow-style semantics) is not captured. On Linux,
only EWMH-managed top-level windows are visible to the window enumeration.

### Cursor highlight

The real mouse cursor is captured and composited into each frame with a
light-yellow highlight around it, so mouse movement is clearly visible. It is
on by default; pass `--no-cursor-highlight` to produce a clean recording without
it. When recording a region or window, the highlight is suppressed while the
cursor is outside the captured area.

### Preview window

```sh
screenrec --preview --duration 30
screenrec --preview-only
```

`--preview` shows a live preview window of the frames being recorded, alongside
encoding them to the video file (off by default, so scripted and headless
recordings never open a window). `--preview-only` shows the capture live in the
preview window without writing a video file. Press **q** in the preview window
to stop the recording gracefully, finalizing the MP4 the same as Ctrl-C. The
preview window requires a display server — a real display on Windows, Xvfb on
Linux.

## Development

The spec and per-ticket issue tracker live under `.scratch/screenrec-cli/`; the
accepted architectural decisions are in `docs/adr/`.
