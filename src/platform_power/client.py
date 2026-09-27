"""GUI-side proxy for talking to the platform-power-daemon system service.

Calls are synchronous: every method here is a single sysfs read/write
forwarded over D-Bus to a local system service, which completes in well
under a millisecond. That's fast enough not to freeze the GTK main loop
for a utility app like this one, and it keeps the calling code (the pages
in pages/) simple and linear instead of callback-shaped.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib

from .daemon import BUS_NAME, IFACE, OBJECT_PATH

log = logging.getLogger("platform-power-client")

# Explicit call timeout rather than the implicit "-1 = proxy/GDBus default"
# used before. Deliberately generous: SetFirmwareAttribute (and, less
# critically, the other setters) trigger a polkit check with
# auth_admin_keep, which shows an interactive password prompt on the
# *daemon* side before the D-Bus call returns to us -- a slow human typing
# a password is not distinguishable from a hung daemon from here, so this
# has to comfortably outlast a real authentication prompt. It only exists
# to turn a truly wedged daemon into a bounded, reported failure instead of
# an indefinite wait, not to make interactive auth feel snappier.
_CALL_TIMEOUT_MS = 60_000


class DaemonUnavailable(Exception):
    pass


class DaemonClient:
    def __init__(self) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                BUS_NAME,
                OBJECT_PATH,
                IFACE,
                None,
            )
        except GLib.Error as exc:  # pragma: no cover - environment dependent
            raise DaemonUnavailable(str(exc)) from exc

        # Deliberately no get_name_owner() check here: the service is
        # D-Bus-activated (see data/dbus/*.service), so it normally has no
        # owner *until* the first real method call triggers systemd to
        # start it. Checking ownership at proxy-construction time would
        # misreport a perfectly healthy, just-not-started-yet daemon as
        # unavailable. Real availability is proven by the first GetState()
        # call succeeding (see window.py's _connect_daemon).

        # A list, not a single slot: both the app (for the tray) and each
        # window register their own StateChanged callback on this same
        # shared DaemonClient. A single `self._on_state_changed = callback`
        # slot here used to mean whichever of the two called
        # watch_state_changed() *last* silently stole every future update
        # from the other -- in practice the window's own call in its
        # __init__ always ran after app.py's, so the tray's callback was
        # overwritten and it never saw another update past app startup.
        self._on_state_changed: list[Callable[[dict], None]] = []
        self._signal_handler_id = self._proxy.connect("g-signal", self._on_g_signal)

    def watch_state_changed(self, callback: Callable[[dict], None]) -> None:
        self._on_state_changed.append(callback)

    def close(self) -> None:
        """Disconnect from the daemon's StateChanged signal.

        Not required for a clean process exit (the whole process is gone a
        moment later anyway), but makes the client's lifetime explicit and
        avoids keeping the proxy/window alive via the signal connection's
        callback reference for longer than necessary if a caller keeps the
        app process running (e.g. tests, or a future embedding scenario).
        """
        if self._signal_handler_id is not None:
            self._proxy.disconnect(self._signal_handler_id)
            self._signal_handler_id = None
        self._on_state_changed = []

    def _on_g_signal(self, proxy, sender_name, signal_name, parameters) -> None:
        if signal_name == "StateChanged" and self._on_state_changed:
            (state_json,) = parameters.unpack()
            state = json.loads(state_json)
            for callback in list(self._on_state_changed):
                callback(state)

    def _call(self, method: str, arg_types: str, args: tuple, reply_types: str = ""):
        try:
            result = self._proxy.call_sync(
                method,
                GLib.Variant(f"({arg_types})", args) if arg_types else None,
                Gio.DBusCallFlags.NONE,
                _CALL_TIMEOUT_MS,
                None,
            )
        except GLib.Error as exc:
            raise RuntimeError(_friendly_dbus_error(exc)) from exc
        return result.unpack() if reply_types else None

    def _call_async(
        self,
        method: str,
        arg_types: str,
        args: tuple,
        reply_types: str = "",
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        def _callback(proxy, result):
            try:
                res = proxy.call_finish(result)
                val = res.unpack() if (reply_types and res) else None
                if on_done:
                    on_done(val)
            except GLib.Error as exc:
                friendly = RuntimeError(_friendly_dbus_error(exc))
                if on_error:
                    on_error(friendly)
                else:
                    # Nothing downstream is listening for this failure: log it
                    # instead of dropping it silently, so a caller that forgot
                    # to pass on_error still leaves a trace of what happened.
                    log.warning("async call %r failed with no on_error handler: %s", method, friendly)

        self._proxy.call(
            method,
            GLib.Variant(f"({arg_types})", args) if arg_types else None,
            Gio.DBusCallFlags.NONE,
            _CALL_TIMEOUT_MS,
            None,
            _callback,
        )

    def get_state(self) -> dict:
        (state_json,) = self._call("GetState", "", (), "s")
        return json.loads(state_json)

    def set_platform_profile(self, profile: str) -> None:
        self._call("SetPlatformProfile", "s", (profile,))

    def set_platform_profile_async(
        self,
        profile: str,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._call_async("SetPlatformProfile", "s", (profile,), on_done=lambda _: on_done() if on_done else None, on_error=on_error)

    def set_charge_thresholds(self, battery: str, start: int, end: int) -> None:
        self._call("SetChargeThresholds", "sii", (battery, start, end))

    def set_charge_thresholds_async(
        self,
        battery: str,
        start: int,
        end: int,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._call_async("SetChargeThresholds", "sii", (battery, start, end), on_done=lambda _: on_done() if on_done else None, on_error=on_error)

    def set_battery_charge_mode(self, mode: str) -> None:
        self._call("SetBatteryChargeMode", "s", (mode,))

    def set_battery_charge_mode_async(
        self,
        mode: str,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._call_async("SetBatteryChargeMode", "s", (mode,), on_done=lambda _: on_done() if on_done else None, on_error=on_error)

    def set_firmware_attribute(self, attribute_id: str, value: str) -> None:
        self._call("SetFirmwareAttribute", "ss", (attribute_id, value))

    def set_firmware_attribute_async(
        self,
        attribute_id: str,
        value: str,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._call_async("SetFirmwareAttribute", "ss", (attribute_id, value), on_done=lambda _: on_done() if on_done else None, on_error=on_error)


def _friendly_dbus_error(exc: GLib.Error) -> str:
    message = exc.message if hasattr(exc, "message") else str(exc)
    if "AccessDenied" in message or "not authorized" in message:
        return "Permission refusée : authentification administrateur requise ou annulée."
    if "Invalid argument" in message or "EINVAL" in message:
        return "Valeur non supportée par le matériel ou le BIOS."
    if "Input/output error" in message or "EIO" in message:
        return "Erreur d'entrée/sortie : le réglage est peut-être verrouillé par le BIOS."
    return message
