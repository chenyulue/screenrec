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

Recording features land ticket by ticket; see `.scratch/screenrec-cli/`.

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
