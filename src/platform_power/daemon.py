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
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            Gio.bus_unown_name(owner_id)
        return 0

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

    def _emit_state_changed(self) -> None:
        if self._connection is None:
            return
        state_json = json.dumps(backend.read_full_state())
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
                invocation.return_value(GLib.Variant("(s)", (state_json,)))
                return

            if method_name == "SetPlatformProfile":
                (profile,) = parameters.unpack()
                check_authorization(connection, sender, f"{_ACTION_PREFIX}.set-thermal-profile")
                backend.set_platform_profile(profile)
                invocation.return_value(None)
                self._emit_state_changed()
                return

            if method_name == "SetChargeThresholds":
                (battery, start, end) = parameters.unpack()
                check_authorization(connection, sender, f"{_ACTION_PREFIX}.set-charge-threshold")
                backend.set_charge_thresholds(battery, start, end)
                invocation.return_value(None)
                self._emit_state_changed()
                return

            if method_name == "SetFirmwareAttribute":
                (attribute_id, value) = parameters.unpack()
                check_authorization(
                    connection, sender, f"{_ACTION_PREFIX}.set-firmware-attribute"
                )
                backend.set_firmware_attribute(attribute_id, value)
                invocation.return_value(None)
                self._emit_state_changed()
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
