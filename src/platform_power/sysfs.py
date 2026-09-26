"""Small, defensive helpers around sysfs file I/O.

Everything in this module is deliberately paranoid: sysfs nodes can
disappear between a listdir() and a read() (hot-unplug, firmware
re-enumeration after suspend, etc.), and writes can be rejected by the
kernel for reasons that have nothing to do with permissions (invalid
value, attribute locked by a BIOS admin password, ...). Callers should
always be prepared to catch OSError.

SECURITY: this module performs NO path validation and NO whitelisting.
write_str() will happily write any value to any path it is given,
including outside FIRMWARE_ATTR_ROOT/POWER_SUPPLY_ROOT/PLATFORM_PROFILE_*.
This is a deliberately dumb, shared low-level I/O primitive -- every
caller (see backend.py) is responsible for validating that a path/value
pair is safe *before* calling write_str(). If you add a new D-Bus method
or backend function that ends up calling write_str() with any part of
the path or value derived from an untrusted caller, you MUST whitelist
it the same way backend.set_firmware_attribute() does (discovery check +
existence check + semantic allow-list), or you will have created a
root-level arbitrary file write.
"""

from __future__ import annotations

import os

FIRMWARE_ATTR_ROOT = "/sys/class/firmware-attributes"
POWER_SUPPLY_ROOT = "/sys/class/power_supply"
PLATFORM_PROFILE_PATH = "/sys/firmware/acpi/platform_profile"
PLATFORM_PROFILE_CHOICES_PATH = "/sys/firmware/acpi/platform_profile_choices"


def read_str(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def read_int(path: str) -> int | None:
    value = read_str(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def write_str(path: str, value: str) -> None:
    """Raises OSError (PermissionError, etc.) on failure. Caller decides how to report it."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(value)


def list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def exists(path: str) -> bool:
    return os.path.exists(path)
