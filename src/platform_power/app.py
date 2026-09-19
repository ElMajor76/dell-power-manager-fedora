from __future__ import annotations

import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio

from .window import PlatformPowerWindow

APP_ID = "io.github.nplacide95.PlatformPower"


class PlatformPowerApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = PlatformPowerWindow(application=self)
        window.present()


def main() -> int:
    return PlatformPowerApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
