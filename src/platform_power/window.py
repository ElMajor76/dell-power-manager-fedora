from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from .client import DaemonClient, DaemonUnavailable
from .pages.battery import BatteryPage
from .pages.firmware import FirmwarePage
from .pages.thermal import ThermalPage


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
            return False
        app = self.get_application()
        if app and getattr(app, "has_tray", False):
            self.set_visible(False)
            return True
        return False

    # -- UI scaffolding -----------------------------------------------------

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self._stack = Adw.ViewStack()
        self._switcher = Adw.ViewSwitcher(stack=self._stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self._switcher)

        self._thermal_page = ThermalPage(self._set_platform_profile)
        self._battery_page = BatteryPage(
            self._set_charge_thresholds,
            self._set_battery_charge_mode,
        )
        self._firmware_page = FirmwarePage(self._set_firmware_attribute)

        self._stack.add_titled_with_icon(
            self._thermal_page, "thermal", "Thermique", "temperature-symbolic"
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

    def _on_action_error(self, exc: Exception) -> None:
        self._show_error(str(exc))
        GLib.idle_add(self._refresh)
