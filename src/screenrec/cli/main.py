"""Argument parsing and entry point for the ``screenrec`` console command."""

import argparse
import sys
import threading
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from screenrec import __version__
from screenrec.capture import (
    FullscreenSource,
    RegionSource,
    WindowRect,
    find_window,
    list_windows,
)
from screenrec.encoder import FfmpegFrameEncoder, NoopFrameEncoder
from screenrec.preview import OpenCvPreview, resolve_placement
from screenrec.session import DefaultRecordingSession


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screenrec",
        description="Cross-platform screen recording CLI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--duration",
        type=float,
        metavar="S",
        help="Record for S seconds, then stop gracefully and finalize the MP4",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        choices=range(1, 61),
        metavar="F",
        help="Frame rate, 1-60 (default: 30)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output MP4 path (default: ./recordings/rec-YYYYMMDD-HHMMSS.mp4)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--monitor",
        type=int,
        default=1,
        metavar="N",
        help="Monitor number to record (default: 1)",
    )
    selection.add_argument(
        "--region",
        type=_region_arg,
        metavar="x,y,w,h",
        help="Record a rectangular region of the screen at x,y with size w,h",
    )
    selection.add_argument(
        "--window",
        metavar="TITLE",
        help="Record the window whose title contains TITLE (region-grab semantics)",
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="List all window titles, then exit (pick a --window TITLE from the list)",
    )
    parser.add_argument(
        "--cursor-highlight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the mouse cursor with a light-yellow highlight (default: on)",
    )
    parser.add_argument(
        "--preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Show a live preview window during recording (default: off)",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Show the capture live in a preview window without writing a video file",
    )

    return parser


def _region_arg(value: str) -> WindowRect:
    """Parse --region x,y,w,h into a WindowRect."""
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected x,y,w,h")
    try:
        left, top, width, height = map(int, parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected integers, got {value!r}") from None
    return WindowRect(left, top, width, height)


def default_output_path() -> Path:
    name = datetime.now().strftime("rec-%Y%m%d-%H%M%S.mp4")
    return Path("recordings") / name


def _stop_on_enter(session: DefaultRecordingSession) -> None:
    """Stop the session when the user presses Enter on stdin."""
    # stdin may be non-interactive: EOF, a closed pipe, or a captured test runner.
    with suppress(OSError, ValueError):
        for _ in sys.stdin:
            session.request_stop()
            break


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)

    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.list_windows:
        try:
            windows = list_windows()
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for title, rect in windows:
            print(f"{title}\t{rect.left},{rect.top},{rect.width},{rect.height}")
        return 0

    if args.region is not None:
        try:
            source = RegionSource(args.region, cursor_highlight=args.cursor_highlight)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    elif args.window is not None:
        try:
            match = find_window(args.window)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if match.warning:
            print(f"warning: {match.warning}", file=sys.stderr)
        source = RegionSource(match.rect, cursor_highlight=args.cursor_highlight)
    else:
        try:
            source = FullscreenSource(args.monitor, cursor_highlight=args.cursor_highlight)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    preview_on = args.preview or args.preview_only

    output: Path | None = None
    if not args.preview_only:
        output = Path(args.output) if args.output else default_output_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        encoder = FfmpegFrameEncoder(source.width, source.height, args.fps, str(output))
    else:
        encoder = NoopFrameEncoder()

    preview = None
    if preview_on:
        position = resolve_placement(source.capture_rect(), source.monitors())
        preview = OpenCvPreview(source.width, source.height, position)
    session = DefaultRecordingSession(
        source, encoder, args.fps, args.duration, preview=preview
    )

    threading.Thread(target=_stop_on_enter, args=(session,), daemon=True).start()

    session.start()
    try:
        session.run()
    except KeyboardInterrupt:
        pass  # Ctrl-C is a graceful stop trigger
    finally:
        session.stop()

    if session.error is not None:
        print(f"error: {session.error}", file=sys.stderr)
        if output is not None:
            print(f"partial output retained: {output}", file=sys.stderr)
        return 1
    if output is not None:
        print(output)
    return 0
