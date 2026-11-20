# Linux display server target: X11

The Linux aarch64 target for this project is an X11 session. mss's Linux capture backends are X11-only (xshmgetimage / xgetimage / xlib) and do not support Wayland; supporting Wayland would mean replacing the whole capture stack with a PipeWire/wlroots protocol implementation, which contradicts the mss-based technology choice. Wayland-only targets are out of scope for v1; users on Wayland must run an X11 session or XWayland (with the caveat that XWayland only captures X11-side windows).

**Status**: accepted
