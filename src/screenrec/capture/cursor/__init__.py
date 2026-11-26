"""Cursor package: real cursor capture and highlight annotation (ticket 06).

Split into two modules by responsibility:
- ``annotation``: the pure geometry that composites the cursor image and
  draws the light-yellow highlight around the cursor position.
- ``platform``: the platform-specific cursor tracking (GLOSSARY: "cursor
  capture") and the mss ``with_cursor`` capability.

The names below keep the import surface of the former single module.
"""

from screenrec.capture.cursor.annotation import (
    HIGHLIGHT_BGRA,
    HIGHLIGHT_RADIUS,
    CursorAnnotator,
    CursorImage,
)

__all__ = ["HIGHLIGHT_BGRA", "HIGHLIGHT_RADIUS", "CursorAnnotator", "CursorImage"]
