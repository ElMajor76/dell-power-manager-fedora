"""GUI-side proxy for talking to the platform-power-daemon system service.

Calls are synchronous: every method here is a single sysfs read/write
forwarded over D-Bus to a local system service, which completes in well
under a millisecond. That's fast enough not to freeze the GTK main loop
for a utility app like this one, and it keeps the calling code (the pages
in pages/) simple and linear instead of callback-shaped.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from gi.repository import Gio, GLib

from .daemon import BUS_NAME, OBJECT_PATH

_IFACE = "io.github.nplacide95.PlatformPower.Daemon1"


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
                _IFACE,
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

        self._on_state_changed: Callable[[dict], None] | None = None
        self._proxy.connect("g-signal", self._on_g_signal)

    def watch_state_changed(self, callback: Callable[[dict], None]) -> None:
        self._on_state_changed = callback

    def _on_g_signal(self, proxy, sender_name, signal_name, parameters) -> None:
        if signal_name == "StateChanged" and self._on_state_changed is not None:
            (state_json,) = parameters.unpack()
            self._on_state_changed(json.loads(state_json))

    def _call(self, method: str, arg_types: str, args: tuple, reply_types: str = ""):
        try:
            result = self._proxy.call_sync(
                method,
                GLib.Variant(f"({arg_types})", args) if arg_types else None,
                Gio.DBusCallFlags.NONE,
                -1,
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
        on_done: Callable[[any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        def _callback(proxy, result):
            try:
                res = proxy.call_finish(result)
                val = res.unpack() if (reply_types and res) else None
                if on_done:
                    on_done(val)
            except GLib.Error as exc:
                if on_error:
                    on_error(RuntimeError(_friendly_dbus_error(exc)))

        self._proxy.call(
            method,
            GLib.Variant(f"({arg_types})", args) if arg_types else None,
            Gio.DBusCallFlags.NONE,
            -1,
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
