from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

_STATUS_LABELS = {
    "Charging": "En charge",
    "Discharging": "Sur batterie",
    "Full": "Pleine",
    "Not charging": "En pause (seuil atteint)",
    "Unknown": "Inconnu",
}


class BatteryPage(Adw.PreferencesPage):
    """Battery health/info + charge-threshold equivalent of Power Manager's
    'Battery Information' and 'Primarily AC use / Custom' screens."""

    __gtype_name__ = "PlatformPowerBatteryPage"

    def __init__(self, on_set_thresholds: Callable[[str, int, int], None]) -> None:
        super().__init__(title="Batterie", icon_name="battery-symbolic")
        self._on_set_thresholds = on_set_thresholds
        self._battery_name: str | None = None
        self._updating = False

        self._info_group = Adw.PreferencesGroup(title="État de la batterie")
        self.add(self._info_group)

        self._row_status = Adw.ActionRow(title="État")
        self._row_capacity = Adw.ActionRow(title="Charge actuelle")
        self._row_health = Adw.ActionRow(title="Santé")
        self._row_cycles = Adw.ActionRow(title="Cycles de charge")
        self._row_model = Adw.ActionRow(title="Modèle")
        for row in (
            self._row_status,
            self._row_capacity,
            self._row_health,
            self._row_cycles,
            self._row_model,
        ):
            self._info_group.add(row)

        self._charge_group = Adw.PreferencesGroup(
            title="Seuils de charge personnalisés",
            description=(
                "Équivalent du mode « Custom » de Dell Power Manager : limite "
                "la charge entre deux seuils pour prolonger la durée de vie de "
                "la batterie, au lieu de toujours charger à 100 %."
            ),
        )
        self.add(self._charge_group)

        self._start_row = Adw.SpinRow.new_with_range(0, 99, 1)
        self._start_row.set_title("Démarrer la charge à (%)")
        self._end_row = Adw.SpinRow.new_with_range(1, 100, 1)
        self._end_row.set_title("Arrêter la charge à (%)")
        self._charge_group.add(self._start_row)
        self._charge_group.add(self._end_row)

        apply_row = Adw.ActionRow(title="Appliquer les seuils")
        self._apply_button = Gtk.Button(
            label="Appliquer", valign=Gtk.Align.CENTER, css_classes=["suggested-action"]
        )
        self._apply_button.connect("clicked", self._on_apply)
        apply_row.add_suffix(self._apply_button)
        self._charge_group.add(apply_row)

        self._unsupported = Adw.StatusPage(
            title="Batterie non détectée",
            description="Aucune batterie compatible n'a été trouvée sur ce système.",
            icon_name="dialog-warning-symbolic",
            visible=False,
        )
        self.add(Adw.PreferencesGroup(child=self._unsupported))

    def update_state(self, batteries: list[dict]) -> None:
        if not batteries:
            self._info_group.set_visible(False)
            self._charge_group.set_visible(False)
            self._unsupported.set_visible(True)
            return

        self._info_group.set_visible(True)
        self._unsupported.set_visible(False)

        # Latitude/Precision machines normally expose a single BAT0; if a
        # system genuinely has two batteries this simply manages the first
        # one, since Dell Power Manager itself doesn't support per-battery
        # thresholds on multi-battery docks either.
        battery = batteries[0]
        self._battery_name = battery["name"]

        status = battery.get("status") or "Unknown"
        self._row_status.set_subtitle(_STATUS_LABELS.get(status, status))
        capacity = battery.get("capacity_percent")
        self._row_capacity.set_subtitle(f"{capacity} %" if capacity is not None else "—")
        health = battery.get("health_percent")
        self._row_health.set_subtitle(f"{health} %" if health is not None else "Non disponible")
        cycles = battery.get("cycle_count")
        self._row_cycles.set_subtitle(str(cycles) if cycles else "Non disponible")
        model = " ".join(filter(None, [battery.get("manufacturer"), battery.get("model_name")]))
        self._row_model.set_subtitle(model or "—")

        supported = battery.get("charge_threshold_supported", False)
        self._charge_group.set_visible(supported)
        if supported:
            self._updating = True
            try:
                start = battery.get("charge_start_threshold") or 0
                end = battery.get("charge_end_threshold") or 100
                self._start_row.set_value(start)
                self._end_row.set_value(end)
            finally:
                self._updating = False

    def _on_apply(self, _button: Gtk.Button) -> None:
        if self._battery_name is None:
            return
        start = int(self._start_row.get_value())
        end = int(self._end_row.get_value())
        if start >= end:
            end = min(100, start + 1)
            self._end_row.set_value(end)
        self._on_set_thresholds(self._battery_name, start, end)
