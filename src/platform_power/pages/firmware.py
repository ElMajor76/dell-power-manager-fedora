from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GObject, Gtk

_CATEGORY_TITLES = {
    "peak_shift": (
        "Peak Shift",
        "Bascule l'alimentation sur batterie pendant les heures de pointe "
        "électrique configurées dans le BIOS.",
    ),
    "advanced_charge": (
        "Charge avancée programmée",
        "Planifie des plages horaires de charge complète de la batterie "
        "(mode Advanced Battery Charge Configuration).",
    ),
    "usb_c": (
        "USB-C & PowerShare",
        "Options d'alimentation et de partage d'énergie des ports USB-C et stations d'accueil.",
    ),
    "power_options": (
        "Options d'alimentation & Allumage",
        "Comportement à l'ouverture du capot, réveil sur secteur (Wake on AC/Dock) et gestion de veille.",
    ),
    "battery_mode": (
        "Mode de charge BIOS",
        "Modes de charge configurés dans le firmware (Adaptive / Express Charge / Primarily AC use).",
    ),
    "thermal": (
        "Gestion thermique BIOS",
        "Réglages de ventilation et historique thermique enregistrés dans le firmware.",
    ),
}

# Preferred display order.
_CATEGORY_ORDER = ["peak_shift", "advanced_charge", "usb_c", "power_options", "battery_mode", "thermal"]


class _AttributeRow:
    """Builds the right Adw row for one firmware attribute and wires it up."""

    def __init__(self, attr: dict, on_set: Callable[[str, str], None]) -> None:
        self.id = attr["id"]
        self._on_set = on_set
        self._updating = False
        self._attr = attr

        attr_type = attr.get("type")
        if attr_type == "enumeration" and attr.get("possible_values"):
            self.widget = Adw.ComboRow(title=attr["display_name"])
            self.widget.set_model(Gtk.StringList.new(attr["possible_values"]))
            self.widget.connect("notify::selected", self._on_enum_changed)
        elif attr_type == "integer":
            lo = attr.get("min_value") if attr.get("min_value") is not None else 0
            hi = attr.get("max_value") if attr.get("max_value") is not None else 100
            step = attr.get("scalar_increment") or 1
            self.widget = Adw.SpinRow.new_with_range(lo, hi, step)
            self.widget.set_title(attr["display_name"])
            self.widget.connect("notify::value", self._on_int_changed)
        else:
            self.widget = Adw.EntryRow(title=attr["display_name"], show_apply_button=True)
            self.widget.connect("apply", self._on_string_apply)

        self.refresh(attr)

    def refresh(self, attr: dict) -> None:
        self._updating = True
        try:
            self._attr = attr
            current = attr.get("current_value")
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
    into the categories Dell Power Manager presents as separate screens.

    Which attributes exist (if any) depends entirely on the machine's BIOS,
    so this page builds itself dynamically from whatever
    /sys/class/firmware-attributes/dell-wmi-sysman/attributes/ reports,
    instead of assuming fixed BIOS token names.
    """

    __gtype_name__ = "PlatformPowerFirmwarePage"

    def __init__(self, on_set_attribute: Callable[[str, str], None]) -> None:
        super().__init__(title="BIOS avancé", icon_name="applications-engineering-symbolic")
        self._on_set_attribute = on_set_attribute
        self._rows: dict[str, _AttributeRow] = {}
        self._groups: dict[str, Adw.PreferencesGroup] = {}

        self._locked_banner = Adw.Banner(
            title=(
                "Un mot de passe administrateur BIOS est défini : certains "
                "réglages ci-dessous peuvent refuser l'écriture."
            )
        )
        self._locked_banner.set_revealed(False)
        self._locked_group = Adw.PreferencesGroup()
        self._locked_group.add(self._locked_banner)
        self.add(self._locked_group)

        for category in _CATEGORY_ORDER:
            title, description = _CATEGORY_TITLES[category]
            group = Adw.PreferencesGroup(title=title, description=description, visible=False)
            self._groups[category] = group
            self.add(group)

        self._empty = Adw.StatusPage(
            title="Aucun attribut BIOS trouvé",
            description=(
                "Le pilote noyau 'dell-wmi-sysman' n'est pas présent, ou ce "
                "modèle n'expose pas ses réglages BIOS via WMI. Ces réglages "
                "resteront accessibles uniquement au démarrage (F2)."
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
            by_category.setdefault(attr.get("category", "other"), []).append(attr)

        for category, group in self._groups.items():
            attrs = by_category.get(category, [])
            group.set_visible(bool(attrs))
            for attr in attrs:
                row = self._rows.get(attr["id"])
                if row is None:
                    row = _AttributeRow(attr, self._on_set_attribute)
                    self._rows[attr["id"]] = row
                    group.add(row.widget)
                else:
                    row.refresh(attr)
