from __future__ import annotations

import logging
import os
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .client import DaemonClient, DaemonUnavailable
from .tray import TrayIndicator
from .window import PlatformPowerWindow

APP_ID = "io.github.nplacide95.PlatformPower"

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
            "Démarrer minimisé dans la zone de notification (systray)",
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

    def _on_close_shortcut(self) -> None:
        if self._window is not None:
            self._window.set_visible(False)

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
        if self._client is not None:
            try:
                self._client.set_platform_profile(profile)
            except Exception as exc:
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
