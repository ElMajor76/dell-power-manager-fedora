from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GObject, Gtk

_CATEGORY_TITLES: dict[str, tuple[str, str]] = {
    "battery_mode": (
        "Mode de charge de la batterie",
        "Configuration de l'algorithme de charge du firmware pour la batterie principale (Adaptatif, Standard, ExpressCharge, etc.).",
    ),
    "advanced_charge": (
        "Charge avancée programmée",
        "Planification des plages horaires et des seuils pour optimiser la durée de vie et la longévité de la batterie.",
    ),
    "peak_shift": (
        "Alimentation aux heures de pointe (Peak Shift)",
        "Bascule automatiquement sur batterie pendant les heures de pointe pour limiter la consommation sur le réseau électrique.",
    ),
    "thermal": (
        "Gestion thermique BIOS",
        "Profils de refroidissement matériels et journal des alertes thermiques enregistrés dans le firmware.",
    ),
    "auto_on": (
        "Démarrage automatique programmé (Auto-On)",
        "Planification de l'allumage automatique du système à des heures et jours précis.",
    ),
    "power_options": (
        "Alimentation, capot & Réveil",
        "Comportement à l'ouverture de l'écran, allumage au branchement secteur et réveil par le réseau (Wake on LAN).",
    ),
    "usb_c": (
        "USB-C & Stations d'accueil (PowerShare)",
        "Options d'alimentation, partage d'énergie PowerShare et réveil via les ports USB-C et stations d'accueil Dell.",
    ),
    "keyboard_backlight": (
        "Rétroéclairage du clavier",
        "Délais d'extinction automatique du rétroéclairage du clavier sur secteur et sur batterie.",
    ),
    "cpu_performance": (
        "Performances & Processeur",
        "Configuration des cœurs de processeur actifs dans le firmware.",
    ),
    "other": (
        "Autres paramètres d'alimentation",
        "Autres réglages d'alimentation exposés par le BIOS.",
    ),
}

# Ordre d'affichage logique et ergonomique des catégories
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
        "Configuration de charge de la batterie",
        "Algorithme de charge du firmware pour la batterie principale",
    ),
    "AdvBatteryChargeCfg": (
        "Charge avancée de la batterie",
        "Active le calendrier de charge avancée pour préserver la durée de vie",
    ),
    "CustomChargeStart": (
        "Seuil de début de charge personnalisé",
        "Pourcentage de batterie auquel la recharge commence (50 à 95 %)",
    ),
    "CustomChargeStop": (
        "Seuil de fin de charge personnalisé",
        "Pourcentage de batterie auquel la recharge s'arrête (55 à 100 %)",
    ),
    "PeakShiftCfg": (
        "Alimentation aux heures de pointe (Peak Shift)",
        "Bascule sur batterie pendant les heures de pointe électrique",
    ),
    "PeakShiftBatteryThreshold": (
        "Seuil minimal de batterie sous Peak Shift",
        "Pourcentage de batterie sous lequel le PC repasse sur secteur",
    ),
    "ThermalManagement": (
        "Profil thermique BIOS",
        "Équilibre matériel entre puissance et refroidissement du firmware",
    ),
    "ThermalLogClear": (
        "Effacer le journal thermique",
        "Efface l'historique des alertes de surchauffe dans le BIOS",
    ),
    "AutoOn": (
        "Mode de démarrage automatique",
        "Jours où l'ordinateur s'allume automatiquement à l'heure définie",
    ),
    "AutoOnHr": (
        "Heure de démarrage automatique (0-23)",
        "Heure d'allumage programmée (format 24 heures)",
    ),
    "AutoOnMn": (
        "Minute de démarrage automatique (0-59)",
        "Minute d'allumage programmée",
    ),
    "AutoOnMon": ("Lundi", "Allumage automatique le lundi"),
    "AutoOnTue": ("Mardi", "Allumage automatique le mardi"),
    "AutoOnWed": ("Mercredi", "Allumage automatique le mercredi"),
    "AutoOnThur": ("Jeudi", "Allumage automatique le jeudi"),
    "AutoOnFri": ("Vendredi", "Allumage automatique le vendredi"),
    "AutoOnSat": ("Samedi", "Allumage automatique le samedi"),
    "AutoOnSun": ("Dimanche", "Allumage automatique le dimanche"),
    "PowerOnLidOpen": (
        "Démarrer à l'ouverture du capot",
        "Allume automatiquement le PC dès l'ouverture de l'écran",
    ),
    "LidSwitch": (
        "Détection de fermeture du capot",
        "Active le capteur de mise en veille à la fermeture de l'écran",
    ),
    "WakeOnAc": (
        "Allumer au branchement secteur",
        "Démarre automatiquement le PC lorsqu'un chargeur est branché",
    ),
    "WakeOnLan": (
        "Réveil par le réseau (Wake on LAN)",
        "Démarre le PC à distance via un paquet réseau Ethernet",
    ),
    "PowerWarn": (
        "Avertissements d'adaptateur secteur",
        "Avertit au démarrage si la puissance du chargeur est insuffisante",
    ),
    "PowerLogClear": (
        "Effacer le journal d'alimentation",
        "Efface l'historique des coupures et événements d'alimentation",
    ),
    "UsbPowerShare": (
        "Partage d'énergie USB PowerShare",
        "Recharge des appareils externes via USB même quand le PC est éteint",
    ),
    "TypeCPower": (
        "Puissance d'alimentation USB-C",
        "Puissance électrique allouée aux périphériques USB-C",
    ),
    "WakeOnDock": (
        "Réveil sur station d'accueil USB-C",
        "Démarre l'ordinateur lors du branchement à une station Dell",
    ),
    "TypeCDockOverride": (
        "Priorité station d'accueil USB-C",
        "Priorise la station d'accueil USB-C connectée",
    ),
    "TypeCDockLan": (
        "Réseau Ethernet de la station d'accueil",
        "Active le port réseau LAN de la station d'accueil USB-C",
    ),
    "TypeCDockAudio": (
        "Audio de la station d'accueil",
        "Active le contrôleur audio de la station d'accueil USB-C",
    ),
    "VideoPowerOnlyPorts": (
        "Ports USB-C vidéo et charge uniquement",
        "Bloque le transfert de données USB pour plus de sécurité",
    ),
    "KbdBacklightTimeoutAc": (
        "Délai d'éclairage clavier (sur secteur)",
        "Temps d'inactivité avant extinction du clavier branché sur secteur",
    ),
    "KbdBacklightTimeoutBatt": (
        "Délai d'éclairage clavier (sur batterie)",
        "Temps d'inactivité avant extinction du clavier sur batterie",
    ),
    "SignOfLifeByKbdBacklight": (
        "Éclairage du clavier au démarrage",
        "Illumine brièvement le clavier dès la mise sous tension (Sign of Life)",
    ),
    "CpuCoreExt": (
        "Sélection des cœurs actifs",
        "Nombre de cœurs processeur activés (laisser au maximum pour les meilleures performances)",
    ),
}

_VALUE_TRANSLATIONS: dict[str, str] = {
    # États binaires
    "Disabled": "Désactivé",
    "Enabled": "Activé",
    "Off": "Désactivé",
    "On": "Activé",
    # Jours et programmation
    "Everyday": "Tous les jours",
    "Weekdays": "Jours de semaine (Lun-Ven)",
    "SelectDays": "Jours sélectionnés",
    # Modes thermiques
    "Optimized": "Optimisé",
    "Cool": "Frais (Ventilation renforcée)",
    "Quiet": "Silencieux",
    "UltraPerformance": "Performances maximales",
    # Modes de charge
    "Adaptive": "Adaptatif",
    "Standard": "Standard",
    "Express": "ExpressCharge",
    "PrimAcUse": "Principalement sur secteur",
    "Custom": "Personnalisé",
    # Réveil réseau
    "LanOnly": "LAN uniquement",
    "LanWithPxeBoot": "LAN avec démarrage réseau PXE",
    # Journaux d'événements
    "Keep": "Conserver le journal",
    "Clear": "Effacer",
    # Délais de rétroéclairage
    "5s": "5 secondes",
    "10s": "10 secondes",
    "15s": "15 secondes",
    "30s": "30 secondes",
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "Never": "Jamais",
    # Puissance électrique
    "7.5W": "7,5 W",
    "15W": "15 W",
    # Niveaux génériques
    "None": "Aucun",
    "All": "Tous",
    "Auto": "Automatique",
    "Low": "Faible",
    "Medium": "Moyen",
    "High": "Élevé",
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
    into well-ordered, user-friendly categories with full French localisation.
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
            title, description = _CATEGORY_TITLES.get(category, (category, ""))
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
