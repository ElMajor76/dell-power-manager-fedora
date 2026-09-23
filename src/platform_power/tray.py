"""Desktop system tray (StatusNotifierItem + DBusMenu) integration.

Provides a tray icon in the system status area (GNOME via AppIndicator
extension, KDE Plasma, XFCE, Sway/Waybar) allowing the user to:
- See the current power profile and battery charge at a glance (tooltip)
- Directly switch thermal/power profiles from the tray menu
- Open the main Platform Power window on click or menu selection
- Cycle profiles with the mouse scroll wheel over the icon
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

log = logging.getLogger("platform-power-tray")

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>

    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg type="s" name="status"/>
    </signal>
    <signal name="NewMenu"/>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>

    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>

    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>

    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>

    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>

    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>

    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>

    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>

    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>

    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>

    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
  </interface>
</node>
"""

_PROFILE_LABELS: dict[str, str] = {
    "cool": "Refroidissement",
    "quiet": "Silencieux",
    "balanced": "Équilibré",
    "performance": "Performances",
}

ID_APP_TITLE = 1
ID_SEP_1 = 2
ID_PROFILE_HEADER = 3
ID_PROFILE_BASE = 10
ID_SEP_2 = 50
ID_OPEN_APP = 51

SNI_PATH = "/io/github/nplacide95/PlatformPower/StatusNotifierItem"
MENU_PATH = "/io/github/nplacide95/PlatformPower/StatusNotifierItem/Menu"


class TrayIndicator:
    """StatusNotifierItem / DBusMenu provider for Linux desktop status trays."""

    def __init__(
        self,
        on_open: Callable[[], None],
        on_set_profile: Callable[[str], None],
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._on_open = on_open
        self._on_set_profile = on_set_profile
        self._on_quit = on_quit

        self._bus: Gio.DBusConnection | None = None
        self._sni_reg_id: int | None = None
        self._menu_reg_id: int | None = None
        self._watcher_sub_id: int | None = None

        self._active_profile: str = "balanced"
        self._choices: list[str] = ["cool", "quiet", "balanced", "performance"]
        self._profile_supported: bool = True
        self._battery_summary: str = ""
        self._revision: int = 1
        self._is_available: bool = False
        self._cached_icon_pixmap: GLib.Variant | None = None

        self._init_dbus()

    @property
    def is_available(self) -> bool:
        return self._is_available

    def _init_dbus(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as exc:
            log.warning("Could not connect to session bus for tray: %s", exc)
            return

        sni_node = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
        menu_node = Gio.DBusNodeInfo.new_for_xml(MENU_XML)

        self._sni_reg_id = self._bus.register_object(
            SNI_PATH,
            sni_node.interfaces[0],
            self._handle_sni_method,
            self._handle_sni_get_prop,
            None,
        )

        self._menu_reg_id = self._bus.register_object(
            MENU_PATH,
            menu_node.interfaces[0],
            self._handle_menu_method,
            self._handle_menu_get_prop,
            None,
        )

        # Re-register whenever a new StatusNotifierHost appears (e.g. extension reload)
        self._watcher_sub_id = self._bus.signal_subscribe(
            "org.kde.StatusNotifierWatcher",
            "org.kde.StatusNotifierWatcher",
            "StatusNotifierHostRegistered",
            "/StatusNotifierWatcher",
            None,
            Gio.DBusSignalFlags.NONE,
            lambda *_: self._register_with_watcher(),
        )

        self._register_with_watcher()

    def _register_with_watcher(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.call(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (SNI_PATH,)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
                self._on_registered_callback,
            )
        except Exception as exc:
            log.debug("Watcher registration call error: %s", exc)

    def _on_registered_callback(self, conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            conn.call_finish(result)
            self._is_available = True
            log.info("Registered Platform Power with StatusNotifierWatcher")
        except Exception as exc:
            log.debug("StatusNotifierWatcher not available: %s", exc)
            self._is_available = False

    def update_state(self, state: dict) -> None:
        changed = False

        prof = state.get("platform_profile", {})
        supported = prof.get("supported", True)
        current = prof.get("current")
        choices = prof.get("choices", [])

        if supported != self._profile_supported:
            self._profile_supported = supported
            changed = True
        if current and current != self._active_profile:
            self._active_profile = current
            changed = True
        if choices and choices != self._choices:
            self._choices = choices
            changed = True

        batteries = state.get("batteries", [])
        if batteries:
            b0 = batteries[0]
            cap = b0.get("capacity_percent")
            status = b0.get("status")
            if cap is not None:
                new_summary = f"{cap}%"
                if status and status not in ("Unknown", "Not charging"):
                    new_summary += f" ({status})"
                if new_summary != self._battery_summary:
                    self._battery_summary = new_summary
                    changed = True

        if changed and self._bus is not None:
            self._revision += 1
            # Notify DBusMenu that layout has updated
            self._bus.emit_signal(
                None,
                MENU_PATH,
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (self._revision, 0)),
            )
            # Notify SNI tooltip changed
            self._bus.emit_signal(
                None,
                SNI_PATH,
                "org.kde.StatusNotifierItem",
                "NewToolTip",
                None,
            )

    def _get_icon_pixmap(self) -> GLib.Variant:
        if self._cached_icon_pixmap is not None:
            return self._cached_icon_pixmap

        pixmaps: list[tuple[int, int, bytes]] = []

        local_icon_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "icons"
        )
        candidates = [
            os.path.join(local_icon_dir, "io.github.nplacide95.PlatformPower.png"),
            os.path.join(local_icon_dir, "io.github.nplacide95.PlatformPower_256.png"),
            "/usr/share/icons/hicolor/256x256/apps/io.github.nplacide95.PlatformPower.png",
            "/usr/share/icons/hicolor/32x32/apps/io.github.nplacide95.PlatformPower.png",
            "/usr/share/pixmaps/io.github.nplacide95.PlatformPower.png",
            os.path.join(local_icon_dir, "io.github.nplacide95.PlatformPower.svg"),
            "/usr/share/icons/hicolor/scalable/apps/io.github.nplacide95.PlatformPower.svg",
        ]

        found_path: str | None = None
        for path in candidates:
            if os.path.isfile(path):
                found_path = path
                break

        if found_path:
            try:
                gi.require_version("GdkPixbuf", "2.0")
                from gi.repository import GdkPixbuf

                for target_sz in (22, 24, 32, 48):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            found_path, target_sz, target_sz, True
                        )
                        if not pb.get_has_alpha():
                            pb = pb.add_alpha(False, 0, 0, 0)
                        w = pb.get_width()
                        h = pb.get_height()
                        stride = pb.get_rowstride()
                        pixels = pb.get_pixels()

                        # SNI spec expects ARGB in network byte order (big-endian: A, R, G, B)
                        argb = bytearray(w * h * 4)
                        for y in range(h):
                            for x in range(w):
                                src = y * stride + x * 4
                                dst = (y * w + x) * 4
                                argb[dst] = pixels[src + 3]      # Alpha
                                argb[dst + 1] = pixels[src]      # Red
                                argb[dst + 2] = pixels[src + 1]  # Green
                                argb[dst + 3] = pixels[src + 2]  # Blue
                        pixmaps.append((w, h, bytes(argb)))
                    except Exception as exc:
                        log.debug(
                            "Error creating pixmap %dx%d from %s: %s",
                            target_sz,
                            target_sz,
                            found_path,
                            exc,
                        )
            except Exception as exc:
                log.debug("GdkPixbuf not available for IconPixmap: %s", exc)

        self._cached_icon_pixmap = GLib.Variant("a(iiay)", pixmaps)
        return self._cached_icon_pixmap

    # -- StatusNotifierItem D-Bus Handlers ----------------------------------

    def _handle_sni_get_prop(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        iface: str,
        prop: str,
    ) -> GLib.Variant | None:
        if prop == "Category":
            return GLib.Variant("s", "Hardware")
        elif prop == "Id":
            return GLib.Variant("s", "io.github.nplacide95.PlatformPower")
        elif prop == "Title":
            return GLib.Variant("s", "Dell Power Manager")
        elif prop == "Status":
            return GLib.Variant("s", "Active")
        elif prop == "IconName":
            return GLib.Variant("s", "io.github.nplacide95.PlatformPower")
        elif prop == "IconPixmap":
            return self._get_icon_pixmap()
        elif prop == "IconThemePath":
            return GLib.Variant("s", "")
        elif prop == "Menu":
            return GLib.Variant("o", MENU_PATH)
        elif prop == "ItemIsMenu":
            return GLib.Variant("b", False)
        elif prop == "ToolTip":
            prof_label = _PROFILE_LABELS.get(
                self._active_profile, self._active_profile.capitalize()
            )
            desc = f"Profil : {prof_label}"
            if self._battery_summary:
                desc += f"  •  Batterie : {self._battery_summary}"
            pixmaps = self._get_icon_pixmap().unpack()
            return GLib.Variant(
                "(sa(iiay)ss)",
                (
                    "io.github.nplacide95.PlatformPower",
                    pixmaps,
                    "Dell Power Manager",
                    desc,
                ),
            )
        return None

    def _handle_sni_method(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        iface: str,
        method: str,
        params: GLib.Variant | None,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self._on_open)
            invocation.return_value(None)
        elif method == "Scroll":
            delta, orientation = params.unpack() if params else (0, "")
            if delta != 0 and self._choices and self._profile_supported:
                try:
                    idx = self._choices.index(self._active_profile)
                    new_idx = (idx + (1 if delta > 0 else -1)) % len(self._choices)
                    new_prof = self._choices[new_idx]
                    GLib.idle_add(self._on_set_profile, new_prof)
                except ValueError:
                    pass
            invocation.return_value(None)
        else:
            invocation.return_value(None)

    # -- DBusMenu Handlers --------------------------------------------------

    def _handle_menu_get_prop(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        iface: str,
        prop: str,
    ) -> GLib.Variant | None:
        if prop == "Version":
            return GLib.Variant("u", 3)
        elif prop == "TextDirection":
            return GLib.Variant("s", "ltr")
        elif prop == "Status":
            return GLib.Variant("s", "normal")
        elif prop == "IconThemePath":
            return GLib.Variant("as", [])
        return None

    def _get_items(self) -> dict[int, dict[str, GLib.Variant]]:
        items: dict[int, dict[str, GLib.Variant]] = {}

        # 1: Title
        items[ID_APP_TITLE] = {
            "label": GLib.Variant("s", "Dell Power Manager"),
            "enabled": GLib.Variant("b", False),
        }
        # 2: Separator
        items[ID_SEP_1] = {"type": GLib.Variant("s", "separator")}

        # 3: Profiles header
        items[ID_PROFILE_HEADER] = {
            "label": GLib.Variant("s", "Profil thermique :"),
            "enabled": GLib.Variant("b", False),
        }

        # 10..: Profile choices
        if self._profile_supported and self._choices:
            for idx, choice in enumerate(self._choices):
                item_id = ID_PROFILE_BASE + idx
                is_selected = choice == self._active_profile
                label = _PROFILE_LABELS.get(choice, choice.capitalize())
                items[item_id] = {
                    "label": GLib.Variant("s", label),
                    "toggle-type": GLib.Variant("s", "checkmark"),
                    "toggle-state": GLib.Variant("i", 1 if is_selected else 0),
                }
        else:
            items[ID_PROFILE_BASE] = {
                "label": GLib.Variant("s", "Non supporté par le matériel"),
                "enabled": GLib.Variant("b", False),
            }

        # 50: Separator
        items[ID_SEP_2] = {"type": GLib.Variant("s", "separator")}

        # 51: Open window
        items[ID_OPEN_APP] = {
            "label": GLib.Variant("s", "Ouvrir Dell Power Manager"),
            "icon-name": GLib.Variant("s", "io.github.nplacide95.PlatformPower"),
        }

        return items

    def _build_layout(self) -> tuple[int, dict[str, GLib.Variant], list]:
        items = self._get_items()
        children = []
        for item_id in sorted(items.keys()):
            children.append(
                GLib.Variant(
                    "(ia{sv}av)",
                    (
                        item_id,
                        items[item_id],
                        [],
                    ),
                )
            )
        return (
            0,
            {"children-display": GLib.Variant("s", "submenu")},
            children,
        )

    def _handle_menu_method(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        path: str,
        iface: str,
        method: str,
        params: GLib.Variant | None,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method == "GetLayout":
            parent_id, depth, prop_names = params.unpack() if params else (0, -1, [])
            layout = self._build_layout()
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self._revision, layout)))
        elif method == "GetGroupProperties":
            ids, prop_names = params.unpack() if params else ([], [])
            items = self._get_items()
            result = []
            for item_id in ids:
                if item_id in items:
                    result.append((item_id, items[item_id]))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))
        elif method == "GetProperty":
            item_id, prop_name = params.unpack() if params else (0, "")
            items = self._get_items()
            val = items.get(item_id, {}).get(prop_name)
            invocation.return_value(GLib.Variant("(v)", (val,)) if val else None)
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        elif method == "Event":
            item_id, event_id, data, timestamp = params.unpack() if params else (0, "", None, 0)
            if event_id == "clicked":
                self._handle_click(item_id)
            invocation.return_value(None)
        elif method == "EventGroup":
            events = params.unpack()[0] if params else []
            for item_id, event_id, data, timestamp in events:
                if event_id == "clicked":
                    self._handle_click(item_id)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        else:
            invocation.return_value(None)

    def _handle_click(self, item_id: int) -> None:
        if ID_PROFILE_BASE <= item_id < ID_PROFILE_BASE + len(self._choices):
            choice = self._choices[item_id - ID_PROFILE_BASE]
            if choice != self._active_profile:
                GLib.idle_add(self._on_set_profile, choice)
        elif item_id == ID_OPEN_APP:
            GLib.idle_add(self._on_open)

    def destroy(self) -> None:
        if self._bus is not None:
            if self._watcher_sub_id:
                self._bus.signal_unsubscribe(self._watcher_sub_id)
                self._watcher_sub_id = None
            if self._sni_reg_id:
                self._bus.unregister_object(self._sni_reg_id)
                self._sni_reg_id = None
            if self._menu_reg_id:
                self._bus.unregister_object(self._menu_reg_id)
                self._menu_reg_id = None
            self._bus = None
