"""Reads and writes the kernel interfaces that actually exist on Linux for
Dell power/thermal management, and turns them into a JSON-friendly shape
the GTK front-end and the D-Bus daemon both understand.

Three independent kernel surfaces are used, because Dell Command | Power
Manager on Windows is really a GUI over three different things underneath:

1. ``/sys/firmware/acpi/platform_profile`` (+ ``..._choices``)
   The generic ACPI platform-profile knob (kernel >= 5.14). This is what
   GNOME's power-profiles-daemon and KDE's Power Management already show
   as "Power Mode" / "Energy Saving / Balanced / Performance". It is the
   closest equivalent to Power Manager's "Thermal Management" slider.

2. ``/sys/class/power_supply/BAT*/charge_control_{start,end}_threshold``
   The standard Linux battery-charge-threshold attribute, supported by
   the ``dell-laptop`` driver on most modern Dell/Latitude/Precision
   machines. Equivalent to Power Manager's "Custom" battery charge
   setting (and used to approximate "Express Charge" / "Adaptive" /
   "Primarily AC use" as threshold presets, since Linux has no separate
   concept of those named modes).

3. ``/sys/class/firmware-attributes/dell-wmi-sysman/attributes/*``
   Dell's BIOS-setup-over-WMI interface, exposed by the in-tree
   ``dell-wmi-sysman`` driver on business-class machines (Latitude,
   Precision, OptiPlex). This is where the BIOS-level extras live:
   Peak Shift, Advanced Battery Charge Configuration (scheduled
   charging), USB-C / Type-C PowerShare, and anything else Dell put in
   BIOS setup. Which attributes actually show up is entirely up to the
   firmware on the machine running this code, so this module discovers
   them at runtime instead of hard-coding attribute names that might be
   wrong for a given BIOS revision. Known attributes are grouped into
   friendly categories by matching on their ``display_name``; anything
   unrecognised still shows up in an "Other BIOS power settings" bucket
   instead of being silently dropped.

This module intentionally does not decide *how* privileged a write is;
callers (the D-Bus daemon) are responsible for polkit checks before
calling any of the ``set_*`` functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import sysfs

# --- Category matching for dell-wmi-sysman attributes ----------------------
#
# Dell does not publish a stable machine-readable list of BIOS token names,
# and they vary across BIOS revisions and product lines. Matching on the
# human-readable display_name substring is the only approach that is not
# tied to one specific firmware dump, and it degrades gracefully: an
# attribute that matches nothing still appears in "other" instead of
# vanishing.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thermal": ("thermal management", "fan", "cooling"),
    "peak_shift": ("peak shift",),
    "advanced_charge": (
        "advanced battery charge",
        "battery charge configuration",
        "custom charge",
        "charging schedule",
    ),
    "usb_c": ("usb powershare", "usb-c", "type-c", "type c", "powershare", "usb wake"),
    "battery_mode": (
        "primarily ac use",
        "primarily ac",
        "express charge",
        "adaptive charging",
        "battery charging mode",
        "charging mode",
    ),
}


def _categorize(display_name: str) -> str:
    name = display_name.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return category
    return "other"


@dataclass
class FirmwareAttribute:
    id: str
    display_name: str
    type: str  # "enumeration" | "integer" | "string" | "unknown"
    current_value: str | None
    possible_values: list[str] = field(default_factory=list)
    min_value: int | None = None
    max_value: int | None = None
    scalar_increment: int | None = None
    category: str = "other"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "type": self.type,
            "current_value": self.current_value,
            "possible_values": self.possible_values,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "scalar_increment": self.scalar_increment,
            "category": self.category,
        }


def find_sysman_root() -> str | None:
    """Locate the dell-wmi-sysman instance directory.

    It is normally ``dell-wmi-sysman`` but some BIOS/driver combinations
    (and the Alienware variant of the driver) register it under a
    slightly different name, so this scans instead of hard-coding it.
    """
    for name in sysfs.list_dir(sysfs.FIRMWARE_ATTR_ROOT):
        if "sysman" in name.lower() or "dell" in name.lower():
            return f"{sysfs.FIRMWARE_ATTR_ROOT}/{name}"
    return None


def read_firmware_attributes() -> list[FirmwareAttribute]:
    root = find_sysman_root()
    if root is None:
        return []
    attrs_dir = f"{root}/attributes"
    result: list[FirmwareAttribute] = []
    for attr_id in sysfs.list_dir(attrs_dir):
        base = f"{attrs_dir}/{attr_id}"
        display_name = sysfs.read_str(f"{base}/display_name") or attr_id
        attr_type = sysfs.read_str(f"{base}/type") or "unknown"
        current_value = sysfs.read_str(f"{base}/current_value")

        possible_values: list[str] = []
        raw_possible = sysfs.read_str(f"{base}/possible_values")
        if raw_possible:
            # dell-wmi-sysman separates choices with ';'
            possible_values = [v for v in raw_possible.split(";") if v]

        result.append(
            FirmwareAttribute(
                id=attr_id,
                display_name=display_name,
                type=attr_type,
                current_value=current_value,
                possible_values=possible_values,
                min_value=sysfs.read_int(f"{base}/min_value"),
                max_value=sysfs.read_int(f"{base}/max_value"),
                scalar_increment=sysfs.read_int(f"{base}/scalar_increment"),
                category=_categorize(display_name),
            )
        )
    return result


def set_firmware_attribute(attr_id: str, value: str) -> None:
    root = find_sysman_root()
    if root is None:
        raise FileNotFoundError("dell-wmi-sysman is not present on this system")
    path = f"{root}/attributes/{attr_id}/current_value"
    if not sysfs.exists(path):
        raise FileNotFoundError(f"unknown firmware attribute: {attr_id}")
    sysfs.write_str(path, value)


def sysman_is_locked() -> bool:
    """True if a BIOS admin password is set and blocking writes.

    dell-wmi-sysman exposes this under <root>/authentication/Admin/is_enabled
    (1/0). If it's set, current_value writes will fail with EIO/EACCES
    until the caller also POSTs the password via the matching
    Update/PendingReboot handshake -- which this tool deliberately does
    not attempt to automate (entering a BIOS admin password through a
    userspace daemon is a bad idea). We only use this to show a clear
    warning in the UI instead of a confusing write failure.
    """
    root = find_sysman_root()
    if root is None:
        return False
    return sysfs.read_str(f"{root}/authentication/Admin/is_enabled") == "1"


# --- ACPI platform profile --------------------------------------------------


def read_platform_profile() -> dict:
    current = sysfs.read_str(sysfs.PLATFORM_PROFILE_PATH)
    choices_raw = sysfs.read_str(sysfs.PLATFORM_PROFILE_CHOICES_PATH) or ""
    choices = choices_raw.split()
    return {
        "supported": current is not None,
        "current": current,
        "choices": choices,
    }


def set_platform_profile(profile: str) -> None:
    if not sysfs.exists(sysfs.PLATFORM_PROFILE_PATH):
        raise FileNotFoundError("platform_profile is not exposed by this kernel/firmware")
    choices = (sysfs.read_str(sysfs.PLATFORM_PROFILE_CHOICES_PATH) or "").split()
    if choices and profile not in choices:
        raise ValueError(f"'{profile}' is not one of {choices}")
    sysfs.write_str(sysfs.PLATFORM_PROFILE_PATH, profile)


# --- Batteries ---------------------------------------------------------------


def _is_battery(name: str) -> bool:
    type_path = f"{sysfs.POWER_SUPPLY_ROOT}/{name}/type"
    return sysfs.read_str(type_path) == "Battery"


def list_batteries() -> list[str]:
    return [n for n in sysfs.list_dir(sysfs.POWER_SUPPLY_ROOT) if _is_battery(n)]


def read_battery(name: str) -> dict:
    base = f"{sysfs.POWER_SUPPLY_ROOT}/{name}"

    energy_full = sysfs.read_int(f"{base}/energy_full") or sysfs.read_int(f"{base}/charge_full")
    energy_full_design = sysfs.read_int(f"{base}/energy_full_design") or sysfs.read_int(
        f"{base}/charge_full_design"
    )
    health_pct = None
    if energy_full and energy_full_design:
        health_pct = round(100 * energy_full / energy_full_design, 1)

    start_threshold = sysfs.read_int(f"{base}/charge_control_start_threshold")
    end_threshold = sysfs.read_int(f"{base}/charge_control_end_threshold")

    return {
        "name": name,
        "model_name": sysfs.read_str(f"{base}/model_name"),
        "manufacturer": sysfs.read_str(f"{base}/manufacturer"),
        "status": sysfs.read_str(f"{base}/status"),  # Charging / Discharging / Full / Not charging
        "capacity_percent": sysfs.read_int(f"{base}/capacity"),
        "cycle_count": sysfs.read_int(f"{base}/cycle_count"),
        "health_percent": health_pct,
        "voltage_now_uv": sysfs.read_int(f"{base}/voltage_now"),
        "power_now_uw": sysfs.read_int(f"{base}/power_now"),
        "charge_threshold_supported": start_threshold is not None and end_threshold is not None,
        "charge_start_threshold": start_threshold,
        "charge_end_threshold": end_threshold,
    }


def set_charge_thresholds(name: str, start: int, end: int) -> None:
    if not (0 <= start < end <= 100):
        raise ValueError("thresholds must satisfy 0 <= start < end <= 100")
    base = f"{sysfs.POWER_SUPPLY_ROOT}/{name}"
    start_path = f"{base}/charge_control_start_threshold"
    end_path = f"{base}/charge_control_end_threshold"
    if not (sysfs.exists(start_path) and sysfs.exists(end_path)):
        raise FileNotFoundError(f"{name} does not expose charge thresholds on this kernel")
    # Lower the end threshold first only when it's safe to do so (avoids a
    # transient state where start > end gets rejected by the driver).
    current_end = sysfs.read_int(end_path) or 100
    if start < current_end:
        sysfs.write_str(start_path, str(start))
        sysfs.write_str(end_path, str(end))
    else:
        sysfs.write_str(end_path, str(end))
        sysfs.write_str(start_path, str(start))


# --- Aggregate state ----------------------------------------------------------


def read_full_state() -> dict:
    return {
        "platform_profile": read_platform_profile(),
        "batteries": [read_battery(n) for n in list_batteries()],
        "firmware_attributes": [a.to_dict() for a in read_firmware_attributes()],
        "firmware_attributes_locked": sysman_is_locked(),
        "sysman_present": find_sysman_root() is not None,
    }
