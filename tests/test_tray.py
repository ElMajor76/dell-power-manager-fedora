from __future__ import annotations

import gi
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
import pytest

from platform_power.tray import (
    TrayIndicator,
    SNI_PATH,
    MENU_PATH,
    ID_OPEN_APP,
)


@pytest.fixture
def tray():
    indicator = TrayIndicator(
        on_open=lambda: None,
        on_set_profile=lambda p: None,
        on_quit=lambda: None,
    )
    yield indicator
    indicator.destroy()


def test_tray_sni_properties(tray):
    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    category = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "Category")
    assert category.unpack() == "Hardware"

    app_id = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "Id")
    assert app_id.unpack() == "io.github.nplacide95.PlatformPower"

    title = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "Title")
    assert title.unpack() == "Dell Power Manager"

    icon_name = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "IconName")
    assert icon_name.unpack() == "io.github.nplacide95.PlatformPower"

    # Crucial: IconThemePath must be empty string so SNI hosts use standard system theme search path
    theme_path = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "IconThemePath")
    assert theme_path.unpack() == ""

    # IconPixmap must return an array of ARGB pixmaps
    icon_pixmap = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "IconPixmap")
    assert icon_pixmap is not None
    pixmaps = icon_pixmap.unpack()
    assert len(pixmaps) > 0
    for w, h, data in pixmaps:
        assert w > 0 and h > 0
        assert len(data) == w * h * 4

    # ToolTip must include app icon name and pixmaps
    tooltip = tray._handle_sni_get_prop(conn, "", SNI_PATH, "org.kde.StatusNotifierItem", "ToolTip")
    assert tooltip is not None
    icon_n, pix_list, t_title, t_desc = tooltip.unpack()
    assert icon_n == "io.github.nplacide95.PlatformPower"
    assert len(pix_list) > 0
    assert "Dell Power Manager" in t_title


def test_tray_dbusmenu_properties(tray):
    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # DBusMenu IconThemePath must be an empty list of strings
    theme_path = tray._handle_menu_get_prop(conn, "", MENU_PATH, "com.canonical.dbusmenu", "IconThemePath")
    assert theme_path.unpack() == []

    items = tray._get_items()
    assert ID_OPEN_APP in items
    assert items[ID_OPEN_APP]["icon-name"].unpack() == "io.github.nplacide95.PlatformPower"
