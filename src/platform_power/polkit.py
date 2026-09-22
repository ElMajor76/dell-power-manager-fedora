"""Minimal synchronous polkit authorization check for a GDBus system-bus
service, talking to org.freedesktop.PolicyKit1 over the same system bus.

We deliberately do the plain, low-level thing (CheckAuthorization on a
unix-process subject built from the caller's PID) rather than pulling in
python3-polkit bindings, which don't reliably exist across distros.
"""

from __future__ import annotations

from gi.repository import Gio, GLib

_POLKIT_BUS_NAME = "org.freedesktop.PolicyKit1"
_POLKIT_OBJECT_PATH = "/org/freedesktop/PolicyKit1/Authority"
_POLKIT_IFACE = "org.freedesktop.PolicyKit1.Authority"


class PolkitDenied(Exception):
    def __init__(self, action_id: str):
        super().__init__(f"not authorized for {action_id}")
        self.action_id = action_id


def check_authorization(
    connection: Gio.DBusConnection,
    sender: str,
    action_id: str,
    interactive: bool = True,
) -> None:
    """Raises PolkitDenied if the caller identified by `sender` (a D-Bus
    unique name) is not authorized for `action_id`. Returns None if OK.

    Uses the native `system-bus-name` Polkit subject, which is verified
    directly by polkitd against dbus-daemon, avoiding PID lookup race conditions.
    """
    subject = (
        "system-bus-name",
        {
            "name": GLib.Variant("s", sender),
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
