"""Minimal synchronous polkit authorization check for a GDBus system-bus
service, talking to org.freedesktop.PolicyKit1 over the same system bus.

We deliberately do the plain, low-level thing (CheckAuthorization on a
unix-process subject built from the caller's PID) rather than pulling in
python3-polkit bindings, which don't reliably exist across distros.
"""

from __future__ import annotations

import time

from gi.repository import Gio, GLib

_POLKIT_BUS_NAME = "org.freedesktop.PolicyKit1"
_POLKIT_OBJECT_PATH = "/org/freedesktop/PolicyKit1/Authority"
_POLKIT_IFACE = "org.freedesktop.PolicyKit1.Authority"


class PolkitDenied(Exception):
    def __init__(self, action_id: str):
        super().__init__(f"not authorized for {action_id}")
        self.action_id = action_id


def _process_start_time(pid: int) -> int:
    with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fh:
        # field 22 (1-indexed) is starttime, but the comm field (2nd) can
        # contain spaces/parens, so split after the closing paren.
        rest = fh.read().rsplit(")", 1)[1].split()
        return int(rest[19])  # index 19 == field 22 minus the 2 consumed (pid, comm)


def check_authorization(
    connection: Gio.DBusConnection, sender: str, action_id: str, interactive: bool = True
) -> None:
    """Raises PolkitDenied if the caller identified by `sender` (a D-Bus
    unique name) is not authorized for `action_id`. Returns None if OK.
    """
    reply = connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "GetConnectionUnixProcessID",
        GLib.Variant("(s)", (sender,)),
        GLib.VariantType("(u)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    (pid,) = reply.unpack()

    try:
        start_time = _process_start_time(pid)
    except (OSError, IndexError, ValueError):
        start_time = 0

    subject = (
        "unix-process",
        {
            "pid": GLib.Variant("u", pid),
            "start-time": GLib.Variant("t", start_time),
        },
    )
    details: dict[str, str] = {}
    flags = 1 if interactive else 0  # AllowUserInteraction = 1

    result = connection.call_sync(
        _POLKIT_BUS_NAME,
        _POLKIT_OBJECT_PATH,
        _POLKIT_IFACE,
        "CheckAuthorization",
        GLib.Variant(
            "((sa{sv})sa{ss}us)",
            (subject, action_id, details, flags, ""),
        ),
        GLib.VariantType("((bba{ss}))"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    ((is_authorized, _is_challenge, _details),) = result.unpack()
    if not is_authorized:
        raise PolkitDenied(action_id)
