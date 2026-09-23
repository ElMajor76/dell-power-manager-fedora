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

# --- Category matching and filtering for dell-wmi-sysman attributes --------
#
# Only attributes genuinely related to power management, thermal, battery,
# and device charging are exposed. Non-power BIOS settings (TPM, Secure Boot,
# remote wipe, BIOS reset, passwords, etc.) are strictly blacklisted.

_FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "reset", "wipe", "password", "pwd", "admin", "setup", "lock",
    "tpm", "secureboot", "tamper", "intrusion", "boot", "uefi", "fota",
    "capsule", "asset", "tag", "service", "macaddr", "ipv", "pxe",
    "wireless", "wlan", "wwan", "bluetooth", "camera", "microphone",
    "fingerprint", "speaker", "audio", "virtualization", "vt", "txt",
    "sata", "raid", "pcie", "dma", "kernel", "abi", "amt", "absolute",
    "telemetry", "hotkey", "supportassist", "recovery", "pending_reboot",
)

_EXEMPT_ATTRIBUTES: set[str] = {
    "TypeCDockAudio",
    "TypeCDockLan",
    "TypeCDockOverride",
}

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "battery_mode": (
        "primarybattcharge",
        "batterychargeconfiguration",
        "battery configuration",
        "charging mode",
        "primarily ac use",
        "express charge",
        "adaptive charging",
    ),
    "peak_shift": (
        "peakshift",
        "peak shift",
    ),
    "advanced_charge": (
        "advbatterycharge",
        "advanced battery charge",
        "customcharge",
        "custom charge",
        "charging schedule",
    ),
    "thermal": (
        "thermalmanagement",
        "thermal management",
        "thermallogclear",
        "fan",
        "cooling",
    ),
    "auto_on": (
        "autoon",
        "auto-on",
        "auto on",
    ),
    "usb_c": (
        "usbpowershare",
        "powershare",
        "usb-c",
        "type-c",
        "type c",
        "typec",
        "wakeondock",
        "videopoweronlyports",
    ),
    "keyboard_backlight": (
        "kbdbacklight",
        "backlighttimeout",
        "signoflifebykbd",
        "keyboard backlight",
    ),
    "cpu_performance": (
        "cpucoreext",
        "active core selection",
        "core selection",
    ),
    "power_options": (
        "poweronlidopen",
        "lidswitch",
        "wakeonac",
        "wakeonlan",
        "blocksleep",
        "powerwarn",
        "powerlogclear",
    ),
}


def _categorize(attr_id: str, display_name: str) -> str | None:
    text = f"{attr_id} {display_name}".lower()

    if attr_id not in _EXEMPT_ATTRIBUTES and any(fb in text for fb in _FORBIDDEN_KEYWORDS):
        return None

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category

    # Only accept in "other" if explicitly matching power/energy/thermal keywords
    if any(k in text for k in ("power", "energy", "battery", "charge", "thermal", "cooling", "sleep", "wake", "ac", "lid")):
        return "power_options"

    return None


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
    """Locate the dell-wmi-sysman instance directory."""
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

        category = _categorize(attr_id, display_name)
        if category is None:
            continue

        attr_type = sysfs.read_str(f"{base}/type") or "unknown"
        current_value = sysfs.read_str(f"{base}/current_value")

        possible_values: list[str] = []
        raw_possible = sysfs.read_str(f"{base}/possible_values")
        if raw_possible:
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
                category=category,
            )
        )
    return result


def set_firmware_attribute(attr_id: str, value: str) -> None:
    root = find_sysman_root()
    if root is None:
        raise FileNotFoundError("dell-wmi-sysman is not present on this system")
    if attr_id not in sysfs.list_dir(f"{root}/attributes"):
        raise FileNotFoundError(f"unknown firmware attribute: {attr_id}")
    base = f"{root}/attributes/{attr_id}"
    if not sysfs.exists(f"{base}/current_value"):
        raise FileNotFoundError(f"unknown firmware attribute: {attr_id}")

    display_name = sysfs.read_str(f"{base}/display_name") or attr_id
    if _categorize(attr_id, display_name) is None:
        raise ValueError(
            f"La modification de l'attribut '{attr_id}' n'est pas autorisée via Dell Power Manager."
        )

    sysfs.write_str(f"{base}/current_value", value)


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

    # Dell BIOS native charge mode if available
    charge_mode = None
    charge_mode_choices: list[str] = []
    sysman = find_sysman_root()
    if sysman:
        mode_path = f"{sysman}/attributes/PrimaryBattChargeCfg"
        if sysfs.exists(mode_path):
            charge_mode = sysfs.read_str(f"{mode_path}/current_value")
            raw_choices = sysfs.read_str(f"{mode_path}/possible_values") or ""
            charge_mode_choices = [c for c in raw_choices.split(";") if c]

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
        "charge_mode": charge_mode,
        "charge_mode_choices": charge_mode_choices,
    }


def set_battery_charge_mode(mode: str) -> None:
    root = find_sysman_root()
    if root is None:
        raise FileNotFoundError("dell-wmi-sysman is not present on this system")
    path = f"{root}/attributes/PrimaryBattChargeCfg/current_value"
    if not sysfs.exists(path):
        raise FileNotFoundError("PrimaryBattChargeCfg is not supported on this machine")
    possible = (sysfs.read_str(f"{root}/attributes/PrimaryBattChargeCfg/possible_values") or "").split(";")
    possible = [p for p in possible if p]
    if possible and mode not in possible:
        raise ValueError(f"'{mode}' is not one of {possible}")
    sysfs.write_str(path, mode)


def set_charge_thresholds(name: str, start: int, end: int) -> None:
    if name not in list_batteries():
        raise FileNotFoundError(f"unknown battery: {name}")

    if not (0 <= start < end <= 100):
        raise ValueError("Le seuil de début doit être inférieur au seuil de fin (entre 0 et 100 %).")
    if (end - start) < 1:
        raise ValueError("L'écart entre le seuil de début et de fin doit être d'au moins 1 %.")

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

    # Synchronize with dell-wmi-sysman if available: Dell firmware requires
    # PrimaryBattChargeCfg to be 'Custom' for custom thresholds to take effect.
    try:
        set_battery_charge_mode("Custom")
    except Exception:
        pass

    root = find_sysman_root()
    if root:
        cust_start = f"{root}/attributes/CustomChargeStart/current_value"
        cust_stop = f"{root}/attributes/CustomChargeStop/current_value"
        if sysfs.exists(cust_start):
            try:
                sysfs.write_str(cust_start, str(start))
            except Exception:
                pass
        if sysfs.exists(cust_stop):
            try:
                sysfs.write_str(cust_stop, str(end))
            except Exception:
                pass


# --- Aggregate state ----------------------------------------------------------


def read_full_state() -> dict:
    return {
        "platform_profile": read_platform_profile(),
        "batteries": [read_battery(n) for n in list_batteries()],
        "firmware_attributes": [a.to_dict() for a in read_firmware_attributes()],
        "firmware_attributes_locked": sysman_is_locked(),
        "sysman_present": find_sysman_root() is not None,
    }
