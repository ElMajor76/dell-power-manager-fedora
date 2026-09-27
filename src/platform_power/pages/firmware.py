from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GObject, Gtk

from ..i18n import _

_CATEGORY_TITLES: dict[str, tuple[str, str]] = {
    "battery_mode": (
        _("Battery charging mode"),
        _("Firmware charging algorithm for the main battery (Adaptive, Standard, ExpressCharge, etc.)."),
    ),
    "advanced_charge": (
        _("Scheduled advanced charging"),
        _("Time windows and thresholds to optimize battery lifespan and longevity."),
    ),
    "peak_shift": (
        _("Peak Shift power"),
        _("Automatically switches to battery during peak electricity hours to reduce grid load."),
    ),
    "thermal": (
        _("BIOS thermal management"),
        _("Hardware cooling profiles and the thermal alert log recorded by the firmware."),
    ),
    "auto_on": (
        _("Scheduled Auto-On"),
        _("Schedules automatic power-on at specific times and days."),
    ),
    "power_options": (
        _("Power, lid and wake"),
        _("Behavior on lid open, power-on when plugged in, and network wake (Wake on LAN)."),
    ),
    "usb_c": (
        _("USB-C and docks (PowerShare)"),
        _("Power options, PowerShare energy sharing, and wake via USB-C ports and Dell docks."),
    ),
    "keyboard_backlight": (
        _("Keyboard backlight"),
        _("Auto-off delays for the keyboard backlight on AC power and on battery."),
    ),
    "cpu_performance": (
        _("Performance and CPU"),
        _("Configuration of active processor cores in the firmware."),
    ),
    "other": (
        _("Other power settings"),
        _("Other power-related settings exposed by the BIOS."),
    ),
}

# Logical, user-friendly display order for categories
_CATEGORY_ORDER: list[str] = [
    "battery_mode",
    "advanced_charge",
    "peak_shift",
    "thermal",
    "auto_on",
    "power_options",
    "usb_c",
    "keyboard_backlight",
    "cpu_performance",
    "other",
]

_ATTR_TO_CATEGORY: dict[str, str] = {
    # battery_mode
    "PrimaryBattChargeCfg": "battery_mode",
    # advanced_charge
    "AdvBatteryChargeCfg": "advanced_charge",
    "CustomChargeStart": "advanced_charge",
    "CustomChargeStop": "advanced_charge",
    # peak_shift
    "PeakShiftCfg": "peak_shift",
    "PeakShiftBatteryThreshold": "peak_shift",
    # thermal
    "ThermalManagement": "thermal",
    "ThermalLogClear": "thermal",
    # auto_on
    "AutoOn": "auto_on",
    "AutoOnHr": "auto_on",
    "AutoOnMn": "auto_on",
    "AutoOnMon": "auto_on",
    "AutoOnTue": "auto_on",
    "AutoOnWed": "auto_on",
    "AutoOnThur": "auto_on",
    "AutoOnFri": "auto_on",
    "AutoOnSat": "auto_on",
    "AutoOnSun": "auto_on",
    # power_options
    "PowerOnLidOpen": "power_options",
    "LidSwitch": "power_options",
    "WakeOnAc": "power_options",
    "WakeOnLan": "power_options",
    "PowerWarn": "power_options",
    "PowerLogClear": "power_options",
    # usb_c
    "UsbPowerShare": "usb_c",
    "TypeCPower": "usb_c",
    "WakeOnDock": "usb_c",
    "TypeCDockOverride": "usb_c",
    "TypeCDockLan": "usb_c",
    "TypeCDockAudio": "usb_c",
    "VideoPowerOnlyPorts": "usb_c",
    # keyboard_backlight
    "KbdBacklightTimeoutAc": "keyboard_backlight",
    "KbdBacklightTimeoutBatt": "keyboard_backlight",
    "SignOfLifeByKbdBacklight": "keyboard_backlight",
    # cpu_performance
    "CpuCoreExt": "cpu_performance",
}

_ATTRIBUTE_SORT_KEYS: dict[str, int] = {
    # battery_mode
    "PrimaryBattChargeCfg": 10,
    # advanced_charge
    "AdvBatteryChargeCfg": 20,
    "CustomChargeStart": 21,
    "CustomChargeStop": 22,
    # peak_shift
    "PeakShiftCfg": 30,
    "PeakShiftBatteryThreshold": 31,
    # thermal
    "ThermalManagement": 40,
    "ThermalLogClear": 41,
    # auto_on
    "AutoOn": 50,
    "AutoOnHr": 51,
    "AutoOnMn": 52,
    "AutoOnMon": 53,
    "AutoOnTue": 54,
    "AutoOnWed": 55,
    "AutoOnThur": 56,
    "AutoOnFri": 57,
    "AutoOnSat": 58,
    "AutoOnSun": 59,
    # power_options
    "PowerOnLidOpen": 60,
    "LidSwitch": 61,
    "WakeOnAc": 62,
    "WakeOnLan": 63,
    "PowerWarn": 64,
    "PowerLogClear": 65,
    # usb_c
    "UsbPowerShare": 70,
    "TypeCPower": 71,
    "WakeOnDock": 72,
    "TypeCDockOverride": 73,
    "TypeCDockLan": 74,
    "TypeCDockAudio": 75,
    "VideoPowerOnlyPorts": 76,
    # keyboard_backlight
    "KbdBacklightTimeoutAc": 80,
    "KbdBacklightTimeoutBatt": 81,
    "SignOfLifeByKbdBacklight": 82,
    # cpu_performance
    "CpuCoreExt": 90,
}

_ATTRIBUTE_METADATA: dict[str, tuple[str, str]] = {
    "PrimaryBattChargeCfg": (
        _("Battery charging configuration"),
        _("Firmware charging algorithm for the main battery"),
    ),
    "AdvBatteryChargeCfg": (
        _("Advanced battery charging"),
        _("Enables the advanced charging schedule to preserve battery lifespan"),
    ),
    "CustomChargeStart": (
        _("Custom charge start threshold"),
        _("Battery percentage at which charging resumes (50 to 95%)"),
    ),
    "CustomChargeStop": (
        _("Custom charge stop threshold"),
        _("Battery percentage at which charging stops (55 to 100%)"),
    ),
    "PeakShiftCfg": (
        _("Peak Shift power"),
        _("Switches to battery during peak electricity hours"),
    ),
    "PeakShiftBatteryThreshold": (
        _("Minimum battery level under Peak Shift"),
        _("Battery percentage below which the PC switches back to AC power"),
    ),
    "ThermalManagement": (
        _("BIOS thermal profile"),
        _("Firmware's hardware balance between power and cooling"),
    ),
    "ThermalLogClear": (
        _("Clear thermal log"),
        _("Clears the overheating alert history stored in the BIOS"),
    ),
    "AutoOn": (
        _("Auto-On mode"),
        _("Days on which the computer powers on automatically at the set time"),
    ),
    "AutoOnHr": (
        _("Auto-On hour (0-23)"),
        _("Scheduled power-on time (24-hour format)"),
    ),
    "AutoOnMn": (
        _("Auto-On minute (0-59)"),
        _("Scheduled power-on minute"),
    ),
    "AutoOnMon": (_("Monday"), _("Automatic power-on on Monday")),
    "AutoOnTue": (_("Tuesday"), _("Automatic power-on on Tuesday")),
    "AutoOnWed": (_("Wednesday"), _("Automatic power-on on Wednesday")),
    "AutoOnThur": (_("Thursday"), _("Automatic power-on on Thursday")),
    "AutoOnFri": (_("Friday"), _("Automatic power-on on Friday")),
    "AutoOnSat": (_("Saturday"), _("Automatic power-on on Saturday")),
    "AutoOnSun": (_("Sunday"), _("Automatic power-on on Sunday")),
    "PowerOnLidOpen": (
        _("Power on when lid opens"),
        _("Automatically turns the PC on as soon as the lid is opened"),
    ),
    "LidSwitch": (
        _("Lid close detection"),
        _("Enables the sleep sensor triggered when the lid is closed"),
    ),
    "WakeOnAc": (
        _("Power on when AC is plugged in"),
        _("Automatically starts the PC when a charger is plugged in"),
    ),
    "WakeOnLan": (
        _("Wake on LAN"),
        _("Starts the PC remotely via a network Ethernet packet"),
    ),
    "PowerWarn": (
        _("AC adapter warnings"),
        _("Warns at startup if the charger's power is insufficient"),
    ),
    "PowerLogClear": (
        _("Clear power log"),
        _("Clears the history of power outages and power events"),
    ),
    "UsbPowerShare": (
        _("USB PowerShare"),
        _("Charges external devices over USB even while the PC is off"),
    ),
    "TypeCPower": (
        _("USB-C power output"),
        _("Electrical power allocated to USB-C peripherals"),
    ),
    "WakeOnDock": (
        _("Wake on USB-C dock"),
        _("Starts the computer when connected to a Dell dock"),
    ),
    "TypeCDockOverride": (
        _("USB-C dock priority"),
        _("Prioritizes the connected USB-C dock"),
    ),
    "TypeCDockLan": (
        _("Dock Ethernet network"),
        _("Enables the LAN network port on the USB-C dock"),
    ),
    "TypeCDockAudio": (
        _("Dock audio"),
        _("Enables the audio controller on the USB-C dock"),
    ),
    "VideoPowerOnlyPorts": (
        _("Video/power-only USB-C ports"),
        _("Blocks USB data transfer for added security"),
    ),
    "KbdBacklightTimeoutAc": (
        _("Keyboard backlight timeout (on AC)"),
        _("Idle time before the keyboard backlight turns off while on AC power"),
    ),
    "KbdBacklightTimeoutBatt": (
        _("Keyboard backlight timeout (on battery)"),
        _("Idle time before the keyboard backlight turns off while on battery"),
    ),
    "SignOfLifeByKbdBacklight": (
        _("Keyboard backlight at startup"),
        _("Briefly lights up the keyboard as soon as it's powered on (Sign of Life)"),
    ),
    "CpuCoreExt": (
        _("Active core selection"),
        _("Number of active processor cores (leave at maximum for best performance)"),
    ),
}

_VALUE_TRANSLATIONS: dict[str, str] = {
    # Scheduling
    "Weekdays": _("Weekdays (Mon-Fri)"),
    "SelectDays": _("Selected days"),
    # Thermal modes
    "Cool": _("Cool (increased fan)"),
    "UltraPerformance": _("Maximum performance"),
    # Charging modes
    "PrimAcUse": _("Primarily AC use"),
    # Network wake
    "LanOnly": _("LAN only"),
    "LanWithPxeBoot": _("LAN with PXE boot"),
    # Event logs
    "Keep": _("Keep log"),
    # Backlight timeouts
    "5s": _("5 seconds"),
    "10s": _("10 seconds"),
    "15s": _("15 seconds"),
    "30s": _("30 seconds"),
    "1m": _("1 minute"),
    "5m": _("5 minutes"),
    "15m": _("15 minutes"),
    "Never": _("Never"),
    # Power
    "7.5W": _("7.5 W"),
    "15W": _("15 W"),
    # Generic levels
    "Auto": _("Automatic"),
}


def _get_attr_info(attr: dict) -> tuple[str, str]:
    attr_id = attr.get("id", "")
    if attr_id in _ATTRIBUTE_METADATA:
        return _ATTRIBUTE_METADATA[attr_id]
    display_name = attr.get("display_name") or attr_id
    return display_name, ""


def _resolve_category(attr: dict) -> str:
    attr_id = attr.get("id", "")
    if attr_id in _ATTR_TO_CATEGORY:
        return _ATTR_TO_CATEGORY[attr_id]
    backend_cat = attr.get("category", "")
    if backend_cat in _CATEGORY_TITLES:
        return backend_cat
    return "other"


class _AttributeRow:
    """Builds the right Adw row for one firmware attribute and wires it up."""

    def __init__(self, attr: dict, on_set: Callable[[str, str], None]) -> None:
        self.id = attr["id"]
        self._on_set = on_set
        self._updating = False
        self._attr = attr

        title, subtitle = _get_attr_info(attr)
        attr_type = attr.get("type")

        if attr_type == "enumeration" and attr.get("possible_values"):
            self.widget = Adw.ComboRow(title=title)
            if subtitle:
                self.widget.set_subtitle(subtitle)
            display_values = [_VALUE_TRANSLATIONS.get(v, v) for v in attr["possible_values"]]
            self.widget.set_model(Gtk.StringList.new(display_values))
            self.widget.connect("notify::selected", self._on_enum_changed)
        elif attr_type == "integer":
            lo = attr.get("min_value") if attr.get("min_value") is not None else 0
            hi = attr.get("max_value") if attr.get("max_value") is not None else 100
            step = attr.get("scalar_increment") or 1
            self.widget = Adw.SpinRow.new_with_range(lo, hi, step)
            self.widget.set_title(title)
            if subtitle:
                self.widget.set_subtitle(subtitle)
            self.widget.connect("notify::value", self._on_int_changed)
        else:
            self.widget = Adw.EntryRow(title=title, show_apply_button=True)
            if subtitle:
                if hasattr(self.widget, "set_subtitle"):
                    self.widget.set_subtitle(subtitle)
                else:
                    self.widget.set_tooltip_text(subtitle)
            self.widget.connect("apply", self._on_string_apply)

        self.refresh(attr)

    def refresh(self, attr: dict) -> None:
        self._updating = True
        try:
            self._attr = attr
            current = attr.get("current_value")
            if current is not None and isinstance(current, str):
                current = current.strip()

            if isinstance(self.widget, Adw.ComboRow):
                values = attr.get("possible_values", [])
                if current in values:
                    self.widget.set_selected(values.index(current))
            elif isinstance(self.widget, Adw.SpinRow):
                try:
                    self.widget.set_value(float(current))
                except (TypeError, ValueError):
                    pass
            elif isinstance(self.widget, Adw.EntryRow):
                self.widget.set_text(current or "")
        finally:
            self._updating = False

    def _on_enum_changed(self, row: Adw.ComboRow, _param: GObject.ParamSpec) -> None:
        if self._updating:
            return
        values = self._attr.get("possible_values", [])
        index = row.get_selected()
        if 0 <= index < len(values):
            self._on_set(self.id, values[index])

    def _on_int_changed(self, row: Adw.SpinRow, _param: GObject.ParamSpec) -> None:
        if self._updating:
            return
        self._on_set(self.id, str(int(row.get_value())))

    def _on_string_apply(self, row: Adw.EntryRow) -> None:
        if self._updating:
            return
        self._on_set(self.id, row.get_text())


class FirmwarePage(Adw.PreferencesPage):
    """Auto-discovered BIOS power attributes from dell-wmi-sysman, grouped
    into well-ordered, user-friendly, translatable categories.
    """

    __gtype_name__ = "PlatformPowerFirmwarePage"

    def __init__(self, on_set_attribute: Callable[[str, str], None]) -> None:
        super().__init__(title=_("Advanced BIOS"), icon_name="applications-engineering-symbolic")
        self._on_set_attribute = on_set_attribute
        self._rows: dict[str, _AttributeRow] = {}
        self._groups: dict[str, Adw.PreferencesGroup] = {}

        self._locked_banner = Adw.Banner(
            title=_(
                "A BIOS administrator password is set: some settings below "
                "may refuse to be written."
            )
        )
        self._locked_banner.set_revealed(False)
        self._locked_group = Adw.PreferencesGroup()
        self._locked_group.add(self._locked_banner)
        self.add(self._locked_group)

        for category in _CATEGORY_ORDER:
            title, description = _CATEGORY_TITLES.get(category, (category, ""))
            group = Adw.PreferencesGroup(title=title, description=description, visible=False)
            self._groups[category] = group
            self.add(group)

        self._empty = Adw.StatusPage(
            title=_("No BIOS attribute found"),
            description=_(
                "The 'dell-wmi-sysman' kernel driver is not present, or this "
                "model doesn't expose its BIOS settings via WMI. These "
                "settings will remain accessible only at boot (F2)."
            ),
            icon_name="dialog-information-symbolic",
            visible=False,
        )
        self._empty_group = Adw.PreferencesGroup()
        self._empty_group.add(self._empty)
        self.add(self._empty_group)

    def update_state(self, attributes: list[dict], locked: bool, sysman_present: bool) -> None:
        self._locked_banner.set_revealed(locked)
        self._locked_group.set_visible(locked)
        is_empty = (sysman_present and not attributes) or not sysman_present
        self._empty.set_visible(is_empty)
        self._empty_group.set_visible(is_empty)

        by_category: dict[str, list[dict]] = {c: [] for c in _CATEGORY_ORDER}
        for attr in attributes:
            cat = _resolve_category(attr)
            by_category.setdefault(cat, []).append(attr)

        for category in _CATEGORY_ORDER:
            group = self._groups.get(category)
            if group is None:
                continue
            attrs = by_category.get(category, [])
            group.set_visible(bool(attrs))
            attrs.sort(
                key=lambda a: (_ATTRIBUTE_SORT_KEYS.get(a["id"], 999), _get_attr_info(a)[0])
            )
            for attr in attrs:
                row = self._rows.get(attr["id"])
                if row is None:
                    row = _AttributeRow(attr, self._on_set_attribute)
                    self._rows[attr["id"]] = row
                    group.add(row.widget)
                else:
                    row.refresh(attr)
