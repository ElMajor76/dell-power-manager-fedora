from __future__ import annotations

import json

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

from platform_power.client import DaemonClient


def _make_client() -> DaemonClient:
    # Bypass __init__ (which opens a real D-Bus proxy to the system bus)
    # entirely: this test is only about the callback-dispatch mechanism in
    # _on_g_signal/watch_state_changed, not about D-Bus connectivity.
    client = DaemonClient.__new__(DaemonClient)
    client._on_state_changed = []
    return client


def test_watch_state_changed_supports_multiple_subscribers():
    # Regression test: watch_state_changed() used to overwrite a single
    # `self._on_state_changed` slot. app.py registers a callback for the
    # tray, then window.py's __init__ registers its own on the *same*
    # shared DaemonClient -- with a single slot, the window's registration
    # silently discarded the tray's, so the tray never saw another
    # StateChanged update past app startup (e.g. the profile checkmark
    # staying stuck after switching profile from the tray menu).
    client = _make_client()

    received_a: list[dict] = []
    received_b: list[dict] = []
    client.watch_state_changed(received_a.append)
    client.watch_state_changed(received_b.append)

    state = {"platform_profile": {"current": "performance"}}
    params = GLib.Variant("(s)", (json.dumps(state),))
    client._on_g_signal(None, ":1.1", "StateChanged", params)

    assert received_a == [state]
    assert received_b == [state]


def test_on_g_signal_ignores_other_signals():
    client = _make_client()
    received: list[dict] = []
    client.watch_state_changed(received.append)

    params = GLib.Variant("(s)", ("{}",))
    client._on_g_signal(None, ":1.1", "SomeOtherSignal", params)

    assert received == []
