"""Test helper for ticket 03: open top-level X11 windows with known titles.

Run under Xvfb (DISPLAY set by the test runner). Prints ``READY`` once the
windows are mapped and registered in the EWMH client list, then stays alive
so the windows exist while the recording runs.

No window manager runs under plain Xvfb, so nothing maintains
``_NET_CLIENT_LIST``; the helper registers its own windows in that property
so ``wmctrl`` can enumerate them.
"""

import ctypes
import ctypes.util
import sys
import time

x11 = ctypes.CDLL(ctypes.util.find_library("X11"))


def _configure_x11(name: str, restype, argtypes):
    func = getattr(x11, name)
    func.restype = restype
    func.argtypes = argtypes
    return func


XOpenDisplay = _configure_x11("XOpenDisplay", ctypes.c_void_p, [ctypes.c_char_p])
XDefaultRootWindow = _configure_x11("XDefaultRootWindow", ctypes.c_ulong, [ctypes.c_void_p])
XCreateSimpleWindow = _configure_x11(
    "XCreateSimpleWindow",
    ctypes.c_ulong,
    [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong,
        ctypes.c_void_p, ctypes.c_ulong,
    ],
)
XMapWindow = _configure_x11("XMapWindow", None, [ctypes.c_void_p, ctypes.c_ulong])
XStoreName = _configure_x11("XStoreName", None, [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p])
XFlush = _configure_x11("XFlush", None, [ctypes.c_void_p])
XInternAtom = _configure_x11("XInternAtom", ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int])
XChangeProperty = _configure_x11(
    "XChangeProperty",
    None,
    [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
    ],
)
XCloseDisplay = _configure_x11("XCloseDisplay", None, [ctypes.c_void_p])


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    display = XOpenDisplay(None)
    if not display:
        print("no X display", file=sys.stderr)
        return 1
    root = XDefaultRootWindow(display)
    atom_client_list = XInternAtom(display, b"_NET_CLIENT_LIST", 0)
    atom_window = XInternAtom(display, b"WINDOW", 0)

    windows = []
    for i in range(1, count + 1):
        title = f"screenrec-test-window-{i}".encode()
        win = XCreateSimpleWindow(display, 0, 10 + 30 * i, 10, 200, 150, 1, 1, None, 0)
        XStoreName(display, win, title)
        XMapWindow(display, win)
        windows.append(win)

    ids = (ctypes.c_ulong * len(windows))(*windows)
    XChangeProperty(display, root, atom_client_list, atom_window, 32, 0, ids, len(windows))
    XFlush(display)
    print("READY", flush=True)
    time.sleep(120)
    XCloseDisplay(display)
    return 0


if __name__ == "__main__":
    sys.exit(main())
