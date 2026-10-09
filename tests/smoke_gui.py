"""GUI smoke test, run by CI (and by hand) under a virtual display:

    PYTHONPATH=src dbus-run-session -- xvfb-run -a /usr/bin/python3 tests/smoke_gui.py

Not collected by pytest (no test_ prefix): it needs a display and runs a
real Gtk main loop. Checks that the window builds and shows with or without
a reachable daemon, and that closing it quits the app when no
StatusNotifierWatcher (tray host) is on the bus, rather than leaving a
hidden process behind. Fails on any GLib CRITICAL (G_DEBUG=fatal-criticals).
"""

import os
import sys

os.environ.setdefault("G_DEBUG", "fatal-criticals")
os.environ.setdefault("GTK_A11Y", "none")

from gi.repository import GLib  # noqa: E402

from platform_power.app import PlatformPowerApp  # noqa: E402

app = PlatformPowerApp()
result: dict[str, bool] = {}


def check() -> bool:
    result["window_visible"] = app._window is not None and app._window.get_visible()
    result["no_tray_detected"] = not app.has_tray
    app._window.close()
    GLib.timeout_add(1500, finish)
    return False


def finish() -> bool:
    result["app_still_running"] = True  # only reached if close did not quit
    app.quit()
    return False


GLib.timeout_add(2500, check)
app.run([])
print(result)
ok = result.get("window_visible") and result.get("no_tray_detected") and "app_still_running" not in result
sys.exit(0 if ok else 1)
