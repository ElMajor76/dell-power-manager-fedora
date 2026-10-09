from __future__ import annotations

import logging
import os
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .client import DaemonClient, DaemonUnavailable
from .i18n import _
from .tray import TrayIndicator
from .window import PlatformPowerWindow

APP_ID = "io.github.nplacide95.PlatformPower"
# Keep in sync with Version: in platform-power-manager.spec and the
# <release version="..."> in data/*.metainfo.xml -- there is no packaging
# step that derives this from either of those, it's just repeated by hand.
APP_VERSION = "0.5.0"

log = logging.getLogger("platform-power")


class PlatformPowerApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.add_main_option(
            "minimized",
            ord("m"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Start minimized in the notification area (systray)"),
            None,
        )
        self._start_minimized: bool = False
        self._tray: TrayIndicator | None = None
        self._window: PlatformPowerWindow | None = None
        self._client: DaemonClient | None = None

    @property
    def has_tray(self) -> bool:
        return self._tray is not None and self._tray.is_available

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        if options.contains("minimized"):
            self._start_minimized = True
        return -1

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        display = Gdk.Display.get_default()
        if display:
            theme = Gtk.IconTheme.get_for_display(display)
            theme.add_search_path("/usr/share/icons")
            local_icon_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "icons"
            )
            if os.path.isdir(local_icon_dir):
                theme.add_search_path(local_icon_dir)

        try:
            self._client = DaemonClient()
            self._client.watch_state_changed(self._on_state_changed)
        except (DaemonUnavailable, RuntimeError) as exc:
            log.warning("Could not connect to platform-power daemon on startup: %s", exc)
            self._client = None

        self._tray = TrayIndicator(
            on_open=self.present_window,
            on_set_profile=self._set_platform_profile,
            on_set_charge_mode=self._set_battery_charge_mode,
        )

        if self._client is not None:
            try:
                state = self._client.get_state()
                self._tray.update_state(state)
            except Exception:
                pass

        close_action = Gio.SimpleAction.new("quit", None)
        close_action.connect("activate", lambda *_: self._on_close_shortcut())
        self.add_action(close_action)
        self.set_accels_for_action("app.quit", ["<primary>q", "<primary>w"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", lambda *_: self._show_about())
        self.add_action(about_action)

        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect(
            "activate", lambda *_: self._window and self._window.refresh_from_menu()
        )
        self.add_action(refresh_action)

        diagnostics_action = Gio.SimpleAction.new("diagnostics", None)
        diagnostics_action.connect(
            "activate", lambda *_: self._window and self._window.show_diagnostics()
        )
        self.add_action(diagnostics_action)

        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect(
            "activate", lambda *_: self._window and self._window.show_shortcuts()
        )
        self.add_action(shortcuts_action)
        self.set_accels_for_action("app.shortcuts", ["<primary>question"])

        docs_action = Gio.SimpleAction.new("docs", None)
        docs_action.connect(
            "activate",
            lambda *_: self._window
            and self._window.open_uri("https://github.com/nplacide95/dell-power-manager-fedora"),
        )
        self.add_action(docs_action)

        report_issue_action = Gio.SimpleAction.new("report-issue", None)
        report_issue_action.connect(
            "activate",
            lambda *_: self._window
            and self._window.open_uri(
                "https://github.com/nplacide95/dell-power-manager-fedora/issues"
            ),
        )
        self.add_action(report_issue_action)

    def _on_close_shortcut(self) -> None:
        # Goes through the window's close-request handler so the "no tray
        # available -> really quit" rule applies to Ctrl+Q/W too.
        if self._window is not None:
            self._window.close()

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name="Dell Power Manager",
            application_icon=APP_ID,
            version=APP_VERSION,
            developer_name="Platform Power contributors",
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/nplacide95/dell-power-manager-fedora",
            issue_url="https://github.com/nplacide95/dell-power-manager-fedora/issues",
            comments=_(
                "Thermal profile, battery charge thresholds and BIOS power "
                "settings for Dell laptops, via standard Linux kernel "
                "interfaces. Independent project, not affiliated with Dell "
                "Technologies."
            ),
        )
        about.present(self._window)

    def do_activate(self) -> None:
        if self._window is None:
            self._window = PlatformPowerWindow(client=self._client, application=self)
            self.hold()

        if not self._start_minimized:
            self.present_window()
        else:
            self._start_minimized = False

    def present_window(self) -> None:
        if self._window is None:
            self._window = PlatformPowerWindow(client=self._client, application=self)
            self.hold()
        self._window.set_visible(True)
        self._window.present()

    def _on_state_changed(self, state: dict) -> None:
        if self._tray is not None:
            self._tray.update_state(state)

    def _set_platform_profile(self, profile: str) -> None:
        # Async, like every other setter (see window.py's comment on why):
        # a synchronous call here would block the GTK main loop for as long
        # as the daemon/polkit take to answer, right from a tray click.
        if self._client is not None:
            self._client.set_platform_profile_async(profile, on_error=self._on_tray_action_error)

    def _set_battery_charge_mode(self, mode: str) -> None:
        if self._client is not None:
            self._client.set_battery_charge_mode_async(mode, on_error=self._on_tray_action_error)

    def _on_tray_action_error(self, exc: Exception) -> None:
        if self._window is not None:
            self._window._show_error(str(exc))

    def quit_application(self) -> None:
        if self._tray is not None:
            self._tray.destroy()
            self._tray = None
        if self._window is not None:
            self._window._quitting = True
            self._window.close()
            self._window = None
        self.quit()


def main() -> int:
    return PlatformPowerApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
