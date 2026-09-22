"""System D-Bus service: io.github.nplacide95.PlatformPower.Daemon1

Runs as root (via the systemd unit in data/systemd/), owns every sysfs
write, and gates each one behind polkit so the unprivileged GTK app never
needs setuid/sudo. Read-only GetState has no polkit check.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from . import backend
from .polkit import PolkitDenied, check_authorization

BUS_NAME = "io.github.nplacide95.PlatformPower.Daemon1"
OBJECT_PATH = "/io/github/nplacide95/PlatformPower/Daemon1"

_ACTION_PREFIX = "io.github.nplacide95.platform-power"

log = logging.getLogger("platform-power-daemon")


def _load_interface_xml() -> str:
    return importlib.resources.files(__package__).joinpath("dbus_iface.xml").read_text(
        encoding="utf-8"
    )


class Daemon:
    def __init__(self) -> None:
        self._connection: Gio.DBusConnection | None = None
        self._registration_id: int | None = None
        self._node_info = Gio.DBusNodeInfo.new_for_xml(_load_interface_xml())
        self._udev_client = None
        self._profile_monitor: Gio.FileMonitor | None = None
        self._debounce_timer_id: int | None = None
        self._last_state_json: str = ""

    def run(self) -> int:
        loop = GLib.MainLoop()
        owner_id = Gio.bus_own_name(
            Gio.BusType.SYSTEM,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )
        self._setup_monitors()
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            if self._debounce_timer_id is not None:
                GLib.source_remove(self._debounce_timer_id)
                self._debounce_timer_id = None
            if self._profile_monitor is not None:
                self._profile_monitor.cancel()
                self._profile_monitor = None
            Gio.bus_unown_name(owner_id)
        return 0

    def _setup_monitors(self) -> None:
        try:
            gi.require_version("GUdev", "1.0")
            from gi.repository import GUdev

            self._udev_client = GUdev.Client.new(["power_supply"])
            self._udev_client.connect("uevent", self._on_uevent)
            log.info("GUdev power_supply monitor initialized")
        except Exception as exc:
            log.warning("Could not initialize GUdev power_supply monitor: %s", exc)

        try:
            prof_file = Gio.File.new_for_path(backend.sysfs.PLATFORM_PROFILE_PATH)
            self._profile_monitor = prof_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._profile_monitor.connect("changed", self._on_file_changed)
            log.info("platform_profile file monitor initialized")
        except Exception as exc:
            log.debug("Could not initialize platform_profile file monitor: %s", exc)

        # Periodic check every 30 seconds as safety sync
        GLib.timeout_add_seconds(30, self._periodic_check)

    def _trigger_debounced_update(self) -> None:
        if self._debounce_timer_id is not None:
            GLib.source_remove(self._debounce_timer_id)
        self._debounce_timer_id = GLib.timeout_add(300, self._on_debounce_timeout)

    def _on_debounce_timeout(self) -> bool:
        self._debounce_timer_id = None
        self._emit_state_changed(force=False)
        return GLib.SOURCE_REMOVE

    def _on_uevent(self, client, action: str, device) -> None:
        self._trigger_debounced_update()

    def _on_file_changed(self, monitor, file, other_file, event_type) -> None:
        if event_type in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CHANGES_DONE_HINT):
            self._trigger_debounced_update()

    def _periodic_check(self) -> bool:
        self._emit_state_changed(force=False)
        return GLib.SOURCE_CONTINUE

    def _on_bus_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        self._connection = connection
        interface = self._node_info.interfaces[0]
        self._registration_id = connection.register_object(
            OBJECT_PATH,
            interface,
            self._handle_method_call,
            None,
            None,
        )
        log.info("acquired %s, object registered at %s", name, OBJECT_PATH)

    def _on_name_lost(self, connection: Gio.DBusConnection, name: str) -> None:
        log.error("lost bus name %s (already running elsewhere?)", name)
        sys.exit(1)

    def _emit_state_changed(self, force: bool = True) -> None:
        if self._connection is None:
            return
        state_json = json.dumps(backend.read_full_state())
        if not force and state_json == self._last_state_json:
            return
        self._last_state_json = state_json
        self._connection.emit_signal(
            None,
            OBJECT_PATH,
            "io.github.nplacide95.PlatformPower.Daemon1",
            "StateChanged",
            GLib.Variant("(s)", (state_json,)),
        )

    def _handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        try:
            if method_name == "GetState":
                state_json = json.dumps(backend.read_full_state())
                self._last_state_json = state_json
                invocation.return_value(GLib.Variant("(s)", (state_json,)))
                return

            if method_name == "SetPlatformProfile":
                (profile,) = parameters.unpack()
                check_authorization(connection, sender, f"{_ACTION_PREFIX}.set-thermal-profile")
                backend.set_platform_profile(profile)
                invocation.return_value(None)
                self._emit_state_changed(force=True)
                return

            if method_name == "SetChargeThresholds":
                (battery, start, end) = parameters.unpack()
                check_authorization(connection, sender, f"{_ACTION_PREFIX}.set-charge-threshold")
                backend.set_charge_thresholds(battery, start, end)
                invocation.return_value(None)
                self._emit_state_changed(force=True)
                return

            if method_name == "SetBatteryChargeMode":
                (mode,) = parameters.unpack()
                check_authorization(connection, sender, f"{_ACTION_PREFIX}.set-charge-threshold")
                backend.set_battery_charge_mode(mode)
                invocation.return_value(None)
                self._emit_state_changed(force=True)
                return

            if method_name == "SetFirmwareAttribute":
                (attribute_id, value) = parameters.unpack()
                check_authorization(
                    connection, sender, f"{_ACTION_PREFIX}.set-firmware-attribute"
                )
                backend.set_firmware_attribute(attribute_id, value)
                invocation.return_value(None)
                self._emit_state_changed(force=True)
                return

            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, "no such method"
            )

        except PolkitDenied as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED, str(exc)
            )
        except (FileNotFoundError, ValueError) as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(exc)
            )
        except OSError as exc:
            log.exception("sysfs write failed for %s", method_name)
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.IO_ERROR, str(exc)
            )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return Daemon().run()


if __name__ == "__main__":
    sys.exit(main())
