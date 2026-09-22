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

_CHARGE_MODE_INFO = {
    "Adaptive": (
        "Adaptatif",
        "Ajuste automatiquement les paramètres de charge selon vos habitudes d'utilisation.",
    ),
    "Standard": (
        "Standard",
        "Charge complètement la batterie à une vitesse standard modérée.",
    ),
    "Express": (
        "ExpressCharge",
        "Charge rapide de la batterie pour un usage nomade ou urgent.",
    ),
    "PrimAcUse": (
        "Principalement sur secteur",
        "Protège la batterie en limitant la charge max pour un PC branché en permanence.",
    ),
    "Custom": (
        "Personnalisé",
        "Définit manuellement les pourcentages de début et de fin de charge.",
    ),
}


class BatteryPage(Adw.PreferencesPage):
    """Battery health/info + charge-threshold equivalent of Power Manager's
    'Battery Information' and 'Primarily AC use / Custom' screens."""

    __gtype_name__ = "PlatformPowerBatteryPage"

    def __init__(
        self,
        on_set_thresholds: Callable[[str, int, int], None],
        on_set_mode: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(title="Batterie", icon_name="battery-symbolic")
        self._on_set_thresholds = on_set_thresholds
        self._on_set_mode = on_set_mode
        self._battery_name: str | None = None
        self._updating = False
        self._charge_modes: list[str] = []

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

        # Mode de charge Dell natif
        self._mode_group = Adw.PreferencesGroup(
            title="Paramètres de charge de la batterie",
            description=(
                "Modes de charge officiels Dell : choisissez le comportement de charge "
                "le plus adapté à votre utilisation."
            ),
        )
        self.add(self._mode_group)

        self._mode_row = Adw.ComboRow(title="Mode de charge")
        self._mode_row.connect("notify::selected", self._on_mode_selected)
        self._mode_group.add(self._mode_row)

        self._mode_desc_row = Adw.ActionRow(title="Description")
        self._mode_group.add(self._mode_desc_row)

        # Seuils personnalisés
        self._charge_group = Adw.PreferencesGroup(
            title="Seuils de charge personnalisés (Custom)",
            description=(
                "Définit manuellement la plage de charge (ex. début à 50 %, arrêt à 80 %) "
                "pour prolonger au maximum la durée de vie de la batterie."
            ),
        )
        self.add(self._charge_group)

        self._start_row = Adw.SpinRow.new_with_range(50, 95, 1)
        self._start_row.set_title("Démarrer la charge à (%)")
        self._end_row = Adw.SpinRow.new_with_range(55, 100, 1)
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
        self._unsupported_group = Adw.PreferencesGroup()
        self._unsupported_group.add(self._unsupported)
        self.add(self._unsupported_group)

    def update_state(self, batteries: list[dict]) -> None:
        if not batteries:
            self._info_group.set_visible(False)
            self._mode_group.set_visible(False)
            self._charge_group.set_visible(False)
            self._unsupported_group.set_visible(True)
            self._unsupported.set_visible(True)
            return

        self._info_group.set_visible(True)
        self._unsupported_group.set_visible(False)
        self._unsupported.set_visible(False)

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

        # Configuration des modes de charge Dell
        modes = battery.get("charge_mode_choices", [])
        current_mode = battery.get("charge_mode")
        has_modes = bool(modes)
        self._mode_group.set_visible(has_modes)

        self._updating = True
        try:
            if has_modes:
                self._charge_modes = modes
                model_list = Gtk.StringList.new(
                    [_CHARGE_MODE_INFO.get(m, (m, ""))[0] for m in modes]
                )
                self._mode_row.set_model(model_list)
                if current_mode in modes:
                    idx = modes.index(current_mode)
                    self._mode_row.set_selected(idx)
                    self._mode_desc_row.set_subtitle(_CHARGE_MODE_INFO.get(current_mode, ("", ""))[1])

            supported = battery.get("charge_threshold_supported", False)
            # Afficher les curseurs personnalisés si le mode est Custom ou s'il n'y a pas de modes BIOS
            is_custom = (not has_modes) or (current_mode == "Custom")
            self._charge_group.set_visible(supported and is_custom)

            if supported:
                start = battery.get("charge_start_threshold") or 50
                end = battery.get("charge_end_threshold") or 100
                self._start_row.set_value(start)
                self._end_row.set_value(end)
        finally:
            self._updating = False

    def _on_mode_selected(self, row: Adw.ComboRow, _param) -> None:
        if self._updating:
            return
        idx = row.get_selected()
        if 0 <= idx < len(self._charge_modes):
            mode = self._charge_modes[idx]
            self._mode_desc_row.set_subtitle(_CHARGE_MODE_INFO.get(mode, ("", ""))[1])
            is_custom = mode == "Custom"
            self._charge_group.set_visible(is_custom)
            if self._on_set_mode:
                self._on_set_mode(mode)

    def _on_apply(self, _button: Gtk.Button) -> None:
        if self._battery_name is None:
            return
        start = int(self._start_row.get_value())
        end = int(self._end_row.get_value())
        if start >= end:
            end = min(100, start + 5)
            self._end_row.set_value(end)
        self._on_set_thresholds(self._battery_name, start, end)
