from __future__ import annotations

import subprocess

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from .client import DaemonClient, DaemonUnavailable
from .pages.battery import BatteryPage
from .pages.firmware import FirmwarePage
from .pages.thermal import ThermalPage, get_thermal_icon

# Keep in sync with app.APP_VERSION (duplicated rather than imported: app.py
# imports this module, so importing back from app would be circular).
_VERSION = "0.3.0"

_DAEMON_UNIT = "platform-power-daemon.service"


class PlatformPowerWindow(Adw.ApplicationWindow):
    __gtype_name__ = "PlatformPowerWindow"

    def __init__(self, client: DaemonClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_default_size(720, 640)
        self.set_title("Dell Power Manager")

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        self._quitting: bool = False
        self.connect("close-request", self._on_close_request)

        self._client: DaemonClient | None = client
        self._last_state: dict | None = None
        self._build_ui()
        if self._client is not None:
            try:
                state = self._client.get_state()
                self._content_bin.set_child(self._stack)
                self._client.watch_state_changed(self._apply_state)
                self._apply_state(state)
            except Exception as exc:
                self._show_unavailable(str(exc))
        else:
            self._connect_daemon()

    def _on_close_request(self, window: Gtk.Window) -> bool:
        if self._quitting:
            if self._client is not None:
                self._client.close()
            return False
        self.set_visible(False)
        return True

    # -- UI scaffolding -----------------------------------------------------

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self._stack = Adw.ViewStack()
        self._switcher = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self._switcher)

        primary_menu = Gio.Menu()

        state_section = Gio.Menu()
        state_section.append("Rafraîchir l'état", "app.refresh")
        state_section.append("Diagnostics", "app.diagnostics")
        primary_menu.append_section(None, state_section)

        help_section = Gio.Menu()
        help_section.append("Raccourcis clavier", "app.shortcuts")
        help_section.append("Documentation", "app.docs")
        help_section.append("Signaler un problème", "app.report-issue")
        primary_menu.append_section(None, help_section)

        about_section = Gio.Menu()
        about_section.append("À propos de Dell Power Manager", "app.about")
        primary_menu.append_section(None, about_section)

        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=primary_menu,
            primary=True,
            tooltip_text="Menu principal",
        )
        header.pack_end(menu_button)

        self._thermal_page = ThermalPage(self._set_platform_profile)
        self._battery_page = BatteryPage(
            self._set_charge_thresholds,
            self._set_battery_charge_mode,
        )
        self._firmware_page = FirmwarePage(self._set_firmware_attribute)

        self._stack.add_titled_with_icon(
            self._thermal_page, "thermal", "Thermique", get_thermal_icon()
        )
        self._stack.add_titled_with_icon(
            self._battery_page, "battery", "Batterie", "battery-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._firmware_page, "firmware", "BIOS avancé", "applications-engineering-symbolic"
        )

        self._content_bin = Adw.Bin(child=self._stack)
        toolbar_view.set_content(self._content_bin)

        self._error_page = Adw.StatusPage(
            title="Service indisponible",
            icon_name="dialog-error-symbolic",
            visible=False,
        )
        retry = Gtk.Button(
            label="Réessayer", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"]
        )
        retry.connect("clicked", lambda _b: self._connect_daemon())
        self._error_page.set_child(retry)

    # -- Daemon connection ----------------------------------------------------

    def _connect_daemon(self) -> None:
        try:
            self._client = DaemonClient()
            # The first GetState() call is what actually proves the daemon
            # is reachable: it's D-Bus-activated, so the proxy alone can't
            # tell us (see the comment in DaemonClient.__init__).
            state = self._client.get_state()
        except (DaemonUnavailable, RuntimeError) as exc:
            self._client = None
            self._show_unavailable(str(exc))
            return

        self._content_bin.set_child(self._stack)
        self._client.watch_state_changed(self._apply_state)
        self._apply_state(state)

    def _show_unavailable(self, detail: str) -> None:
        self._error_page.set_description(
            "Impossible de contacter platform-power-daemon.\n"
            f"{detail}\n\n"
            "Vérifiez : systemctl status platform-power-daemon"
        )
        self._content_bin.set_child(self._error_page)
        self._error_page.set_visible(True)

    def _refresh(self) -> None:
        if self._client is None:
            return
        try:
            state = self._client.get_state()
        except RuntimeError as exc:
            self._show_error(str(exc))
            return
        self._apply_state(state)

    def _apply_state(self, state: dict) -> None:
        self._last_state = state
        self._thermal_page.update_state(state.get("platform_profile", {}))
        self._battery_page.update_state(state.get("batteries", []))
        self._firmware_page.update_state(
            state.get("firmware_attributes", []),
            state.get("firmware_attributes_locked", False),
            state.get("sysman_present", False),
        )

    def _show_error(self, message: str) -> None:
        toast = Adw.Toast(title=message, timeout=5)
        self._toast_overlay.add_toast(toast)

    # -- Actions (each call is asynchronous so Polkit auth or slow BIOS
    #    writes never freeze the GTK main loop) ----------------------------

    def _set_platform_profile(self, profile: str) -> None:
        if self._client is None:
            return
        self._client.set_platform_profile_async(
            profile,
            on_done=self._on_action_success,
            on_error=self._on_action_error,
        )

    def _set_charge_thresholds(self, battery: str, start: int, end: int) -> None:
        if self._client is None:
            return
        self._client.set_charge_thresholds_async(
            battery,
            start,
            end,
            on_done=self._on_action_success,
            on_error=self._on_action_error,
        )

    def _set_battery_charge_mode(self, mode: str) -> None:
        if self._client is None:
            return
        self._client.set_battery_charge_mode_async(
            mode,
            on_done=self._on_action_success,
            on_error=self._on_action_error,
        )

    def _set_firmware_attribute(self, attribute_id: str, value: str) -> None:
        if self._client is None:
            return
        self._client.set_firmware_attribute_async(
            attribute_id,
            value,
            on_done=self._on_action_success,
            on_error=self._on_action_error,
        )

    def _on_action_success(self) -> None:
        GLib.idle_add(self._refresh)

    def _on_action_error(self, exc: RuntimeError) -> None:
        self._show_error(str(exc))
        GLib.idle_add(self._refresh)

    # -- Menu actions (Rafraîchir / Diagnostics / Raccourcis / liens) -------

    def refresh_from_menu(self) -> None:
        """Like _refresh(), but for the explicit "Rafraîchir l'état" menu
        item: give visible feedback either way, since a manual refresh that
        appears to do nothing (when nothing actually changed) reads as
        broken rather than as "already up to date"."""
        if self._client is None:
            self._show_error("Aucune connexion au service pour l'instant.")
            return
        try:
            state = self._client.get_state()
        except RuntimeError as exc:
            self._show_error(str(exc))
            return
        self._apply_state(state)
        toast = Adw.Toast(title="État actualisé", timeout=2)
        self._toast_overlay.add_toast(toast)

    def show_diagnostics(self) -> None:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", _DAEMON_UNIT],
                capture_output=True,
                text=True,
                timeout=2,
            )
            daemon_status = result.stdout.strip() or "inconnu"
        except Exception:
            daemon_status = "inconnu"

        state = self._last_state or {}
        sysman_present = state.get("sysman_present", False)
        firmware_count = len(state.get("firmware_attributes", []))
        firmware_locked = state.get("firmware_attributes_locked", False)

        dialog = Adw.Dialog(title="Diagnostics", content_width=440)
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        page.add(group)
        dialog.set_child(page)

        def row(title: str, subtitle: str) -> None:
            group.add(Adw.ActionRow(title=title, subtitle=subtitle))

        row("Version installée", _VERSION)
        row(
            "Service platform-power-daemon",
            "Actif" if daemon_status == "active" else f"Inactif ({daemon_status})",
        )
        row("Connexion D-Bus", "Établie" if self._client is not None else "Indisponible")
        row(
            "BIOS dell-wmi-sysman détecté",
            "Oui" if sysman_present else "Non (fonctions BIOS avancées indisponibles)",
        )
        if sysman_present:
            row("Attributs BIOS exposés", str(firmware_count))
            row(
                "Réglages BIOS verrouillés",
                "Oui (mot de passe administrateur BIOS actif)" if firmware_locked else "Non",
            )

        dialog.present(self)

    def show_shortcuts(self) -> None:
        builder = Gtk.Builder()
        builder.add_from_string(
            """
            <interface>
              <object class="GtkShortcutsWindow" id="shortcuts">
                <property name="modal">1</property>
                <child>
                  <object class="GtkShortcutsSection">
                    <property name="visible">1</property>
                    <child>
                      <object class="GtkShortcutsGroup">
                        <property name="title" translatable="no">Général</property>
                        <child>
                          <object class="GtkShortcutsShortcut">
                            <property name="title" translatable="no">Masquer la fenêtre (l'application continue en arrière-plan)</property>
                            <property name="accelerator">&lt;primary&gt;q &lt;primary&gt;w</property>
                          </object>
                        </child>
                        <child>
                          <object class="GtkShortcutsShortcut">
                            <property name="title" translatable="no">Afficher les raccourcis clavier</property>
                            <property name="accelerator">&lt;primary&gt;question</property>
                          </object>
                        </child>
                      </object>
                    </child>
                  </object>
                </child>
              </object>
            </interface>
            """
        )
        shortcuts = builder.get_object("shortcuts")
        shortcuts.set_transient_for(self)
        shortcuts.present()

    def open_uri(self, uri: str) -> None:
        Gtk.UriLauncher(uri=uri).launch(self, None, None)
