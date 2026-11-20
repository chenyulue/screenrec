"""Argument parsing and entry point for the ``screenrec`` console command."""

import argparse
import sys
from collections.abc import Sequence

from screenrec import __version__


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0
    parser.parse_args(argv)
    return 0
