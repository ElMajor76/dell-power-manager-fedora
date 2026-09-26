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
    ID_PROFILE_HEADER,
    ID_PROFILE_BASE,
    ID_CHARGE_MODE_HEADER,
    ID_CHARGE_MODE_BASE,
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

    # Ensure there is NO 'Quitter' option in the system tray menu
    for item in items.values():
        if "label" in item:
            assert "quitter" not in item["label"].unpack().lower()


def test_tray_profile_and_charge_mode_are_flyout_submenus(tray):
    tray.update_state(
        {
            "platform_profile": {
                "supported": True,
                "current": "balanced",
                "choices": ["cool", "quiet", "balanced", "performance"],
            },
            "batteries": [
                {
                    "capacity_percent": 87,
                    "status": "Charging",
                    "charge_mode": "Adaptive",
                    "charge_mode_choices": ["Adaptive", "Standard", "Express", "PrimAcUse", "Custom"],
                }
            ],
        }
    )

    root_id, root_props, root_children = tray._build_layout()
    assert root_id == 0
    root_child_ids = [c.unpack()[0] for c in root_children]

    # Both headers are top-level entries in the root menu ...
    assert ID_PROFILE_HEADER in root_child_ids
    assert ID_CHARGE_MODE_HEADER in root_child_ids
    # ... and are marked as flyout submenus, not flat radio-style entries.
    profile_header = next(c.unpack() for c in root_children if c.unpack()[0] == ID_PROFILE_HEADER)
    assert profile_header[1]["children-display"] == "submenu"
    charge_header = next(c.unpack() for c in root_children if c.unpack()[0] == ID_CHARGE_MODE_HEADER)
    assert charge_header[1]["children-display"] == "submenu"

    # The actual choices are NOT flat root-level entries anymore ...
    assert ID_PROFILE_BASE not in root_child_ids
    assert ID_CHARGE_MODE_BASE not in root_child_ids
    # ... they are nested under their respective submenu.
    _, _, profile_children = profile_header
    assert [c[0] for c in profile_children] == [ID_PROFILE_BASE + i for i in range(4)]
    _, _, charge_children = charge_header
    assert [c[0] for c in charge_children] == [ID_CHARGE_MODE_BASE + i for i in range(5)]

    # GetLayout must also work when a host asks for a submenu directly by id
    # (lazy-loading hosts), not just when it fetches everything from root.
    # Unlike root_children above, these come straight from _build_layout()
    # (not re-unpacked), so they are still GLib.Variant-wrapped.
    sub_id, sub_props, sub_children = tray._build_layout(parent_id=ID_PROFILE_HEADER, recursion_depth=-1)
    assert sub_id == ID_PROFILE_HEADER
    assert [c.unpack()[0] for c in sub_children] == [ID_PROFILE_BASE + i for i in range(4)]
