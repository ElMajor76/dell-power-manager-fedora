from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GObject, Gtk

from ..i18n import _

# ACPI platform_profile choices as defined by the kernel
# (Documentation/ABI/testing/sysfs-platform_profile), with the labels
# Dell's own tools use for the equivalent thermal presets.
_PROFILE_LABELS = {
    "low-power": _("Power saver"),
    "quiet": _("Quiet"),
    "cool": _("Cool"),
    "balanced": _("Balanced"),
    "balanced-performance": _("Balanced performance"),
    "performance": _("Maximum performance"),
}


def get_thermal_icon() -> str:
    """Return temperature-symbolic if available in the theme, otherwise balanced power profile icon."""
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        if theme.has_icon("temperature-symbolic"):
            return "temperature-symbolic"
    return "power-profile-balanced-symbolic"


class ThermalPage(Adw.PreferencesPage):
    __gtype_name__ = "PlatformPowerThermalPage"

    def __init__(self, on_set_profile: Callable[[str], None]) -> None:
        super().__init__(title=_("Thermal"), icon_name=get_thermal_icon())
        self._on_set_profile = on_set_profile
        self._choices: list[str] = []
        self._updating = False

        self._group = Adw.PreferencesGroup(
            title=_("Thermal management"),
            description=_(
                "Equivalent to Dell Power Manager's \"Thermal Management\" "
                "setting. Adjusts the balance between performance and fan "
                "noise/temperature via the platform's ACPI profile."
            ),
        )
        self.add(self._group)

        self._row = Adw.ComboRow(title=_("Profile"))
        self._row.connect("notify::selected", self._on_selected)
        self._group.add(self._row)

        self._unsupported = Adw.StatusPage(
            title=_("Not available"),
            description=_(
                "This kernel/firmware does not expose "
                "/sys/firmware/acpi/platform_profile. Update the BIOS and "
                "kernel, or check that the 'dell-laptop' module is loaded."
            ),
            icon_name="dialog-warning-symbolic",
            visible=False,
        )
        self._unsupported_group = Adw.PreferencesGroup()
        self._unsupported_group.add(self._unsupported)
        self.add(self._unsupported_group)

    def update_state(self, platform_profile: dict) -> None:
        self._updating = True
        try:
            supported = platform_profile.get("supported", False)
            self._group.set_visible(supported)
            self._unsupported_group.set_visible(not supported)
            self._unsupported.set_visible(not supported)
            if not supported:
                return

            self._choices = platform_profile.get("choices", [])
            model = Gtk.StringList.new(
                [_PROFILE_LABELS.get(c, c) for c in self._choices]
            )
            self._row.set_model(model)

            current = platform_profile.get("current")
            if current in self._choices:
                self._row.set_selected(self._choices.index(current))
        finally:
            self._updating = False

    def _on_selected(self, row: Adw.ComboRow, _param: GObject.ParamSpec) -> None:
        if self._updating:
            return
        index = row.get_selected()
        if 0 <= index < len(self._choices):
            self._on_set_profile(self._choices[index])
