"""Desktop system tray (StatusNotifierItem + DBusMenu) integration.

Provides a tray icon in the system status area (GNOME via AppIndicator
extension, KDE Plasma, XFCE, Sway/Waybar) allowing the user to:
- See the current power profile and battery charge at a glance (menu label
  and tooltip, no need to open the window)
- Directly switch thermal/power profiles from the tray menu
- Directly switch battery charge mode from the tray menu (Adaptive/
  Standard/ExpressCharge/PrimAcUse/Custom), when the firmware exposes it
- Open the main Platform Power window on click or menu selection
- Cycle profiles with the mouse scroll wheel over the icon

No "Quit" entry is offered here by design: like the window's close button
(which only hides it), this is meant to behave as a persistent system
service. See tests/test_tray.py for the regression test guarding this.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

from .i18n import _

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
    "cool": _("Cool"),
    "quiet": _("Quiet"),
    "balanced": _("Balanced"),
    "performance": _("Performance"),
}

# Short labels only, kept in sync with the longer (label, description) pairs
# in pages/battery.py's _CHARGE_MODE_INFO -- same duplication trade-off as
# _PROFILE_LABELS above vs. pages/thermal.py, so the tray stays a
# self-contained D-Bus service with no GTK page imports.
_CHARGE_MODE_LABELS: dict[str, str] = {
    "Adaptive": _("Adaptive"),
    "Standard": _("Standard"),
    "Express": _("ExpressCharge"),
    "PrimAcUse": _("Primarily AC use"),
    "Custom": _("Custom"),
}

ID_APP_TITLE = 1
ID_SEP_1 = 2
ID_BATTERY_INFO = 3
ID_PROFILE_HEADER = 4
ID_PROFILE_BASE = 10
ID_SEP_2 = 50
ID_CHARGE_MODE_HEADER = 51
ID_CHARGE_MODE_BASE = 60
ID_SEP_3 = 100
ID_OPEN_APP = 101

SNI_PATH = "/io/github/nplacide95/PlatformPower/StatusNotifierItem"
MENU_PATH = "/io/github/nplacide95/PlatformPower/StatusNotifierItem/Menu"


class TrayIndicator:
    """StatusNotifierItem / DBusMenu provider for Linux desktop status trays."""

    def __init__(
        self,
        on_open: Callable[[], None],
        on_set_profile: Callable[[str], None],
        on_set_charge_mode: Callable[[str], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._on_open = on_open
        self._on_set_profile = on_set_profile
        self._on_set_charge_mode = on_set_charge_mode
        self._on_quit = on_quit

        self._bus: Gio.DBusConnection | None = None
        self._sni_reg_id: int | None = None
        self._menu_reg_id: int | None = None
        self._watcher_sub_id: int | None = None
        self._watcher_name_id: int | None = None

        self._active_profile: str = "balanced"
        self._choices: list[str] = ["cool", "quiet", "balanced", "performance"]
        self._profile_supported: bool = True
        self._battery_summary: str = ""
        self._charge_mode: str | None = None
        self._charge_mode_choices: list[str] = []
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

        # Also follow the watcher's *name* appearing/vanishing. On a desktop
        # session start (notably Ubuntu's GNOME, where the AppIndicator
        # extension only claims org.kde.StatusNotifierWatcher once
        # gnome-shell has loaded it) the autostarted app routinely comes up
        # before any watcher exists, so the first registration fails; the
        # same applies to a shell/Plasma restart. Registering when the name
        # appears makes the tray icon show up without restarting the app.
        self._watcher_name_id = Gio.bus_watch_name_on_connection(
            self._bus,
            "org.kde.StatusNotifierWatcher",
            Gio.BusNameWatcherFlags.NONE,
            lambda *_: self._register_with_watcher(),
            lambda *_: self._on_watcher_vanished(),
        )

    def _on_watcher_vanished(self) -> None:
        self._is_available = False

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
        # (item_id, toggle-state) pairs for entries whose checkmark flips.
        # This is reported via ItemsPropertiesUpdated, which is what
        # DBusMenu hosts (the GNOME Shell AppIndicator extension, KDE
        # Plasma, XFCE) actually watch to live-refresh a toggle-state on an
        # *already open* submenu. LayoutUpdated alone (emitted below
        # regardless, for hosts that only refetch on next open/close) is
        # about structural changes and is not reliably enough to flip an
        # existing checkmark while the submenu is currently visible -- this
        # is exactly why the checkmark used to appear stuck after switching
        # profile/charge mode from an already-open tray menu.
        toggle_updates: list[tuple[int, dict[str, GLib.Variant]]] = []

        prof = state.get("platform_profile", {})
        supported = prof.get("supported", True)
        current = prof.get("current")
        choices = prof.get("choices", [])
        effective_choices = choices or self._choices

        if supported != self._profile_supported:
            self._profile_supported = supported
            changed = True
        if current and current != self._active_profile:
            if self._active_profile in effective_choices:
                old_idx = effective_choices.index(self._active_profile)
                toggle_updates.append(
                    (ID_PROFILE_BASE + old_idx, {"toggle-state": GLib.Variant("i", 0)})
                )
            self._active_profile = current
            if current in effective_choices:
                new_idx = effective_choices.index(current)
                toggle_updates.append(
                    (ID_PROFILE_BASE + new_idx, {"toggle-state": GLib.Variant("i", 1)})
                )
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

            mode = b0.get("charge_mode")
            mode_choices = b0.get("charge_mode_choices", [])
            effective_mode_choices = mode_choices or self._charge_mode_choices
            if mode != self._charge_mode:
                if self._charge_mode in effective_mode_choices:
                    old_idx = effective_mode_choices.index(self._charge_mode)
                    toggle_updates.append(
                        (ID_CHARGE_MODE_BASE + old_idx, {"toggle-state": GLib.Variant("i", 0)})
                    )
                self._charge_mode = mode
                if mode in effective_mode_choices:
                    new_idx = effective_mode_choices.index(mode)
                    toggle_updates.append(
                        (ID_CHARGE_MODE_BASE + new_idx, {"toggle-state": GLib.Variant("i", 1)})
                    )
                changed = True
            if mode_choices != self._charge_mode_choices:
                self._charge_mode_choices = mode_choices
                changed = True

        if changed and self._bus is not None:
            self._revision += 1

            if toggle_updates:
                self._bus.emit_signal(
                    None,
                    MENU_PATH,
                    "com.canonical.dbusmenu",
                    "ItemsPropertiesUpdated",
                    GLib.Variant("(a(ia{sv})a(ias))", (toggle_updates, [])),
                )

            # Notify DBusMenu that layout has updated too, for hosts that
            # only rely on this (e.g. to refresh on next open rather than
            # live).
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
            desc = _("Profile: {profile}").format(profile=prof_label)
            if self._battery_summary:
                desc += "  •  " + _("Battery: {summary}").format(summary=self._battery_summary)
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

    def _get_tree(self) -> tuple[dict[int, dict[str, GLib.Variant]], dict[int, list[int]]]:
        """Build the full set of item properties plus the parent -> ordered
        children-ids mapping that turns thermal profile and charge mode
        each into a proper DBusMenu flyout submenu, instead of a flat list
        of radio-style entries inline in the root menu."""
        items: dict[int, dict[str, GLib.Variant]] = {}
        children: dict[int, list[int]] = {0: []}

        def add(item_id: int, props: dict[str, GLib.Variant], parent: int = 0) -> None:
            items[item_id] = props
            children.setdefault(parent, []).append(item_id)
            children.setdefault(item_id, [])

        # 1: Title
        add(
            ID_APP_TITLE,
            {"label": GLib.Variant("s", _("Dell Power Manager")), "enabled": GLib.Variant("b", False)},
        )
        # 2: Separator
        add(ID_SEP_1, {"type": GLib.Variant("s", "separator")})

        # 3: Battery status, at-a-glance (no need to open the window or wait
        # for the tooltip to hover-trigger)
        if self._battery_summary:
            add(
                ID_BATTERY_INFO,
                {
                    "label": GLib.Variant(
                        "s", _("Battery: {summary}").format(summary=self._battery_summary)
                    ),
                    "enabled": GLib.Variant("b", False),
                },
            )

        # 4: "Profil thermique" submenu. When the platform doesn't support
        # profile switching at all, show a single disabled explanatory
        # entry instead of an (empty or dead) submenu.
        if self._profile_supported and self._choices:
            add(
                ID_PROFILE_HEADER,
                {
                    "label": GLib.Variant("s", _("Thermal profile")),
                    "children-display": GLib.Variant("s", "submenu"),
                },
            )
            for idx, choice in enumerate(self._choices):
                item_id = ID_PROFILE_BASE + idx
                is_selected = choice == self._active_profile
                label = _PROFILE_LABELS.get(choice, choice.capitalize())
                add(
                    item_id,
                    {
                        "label": GLib.Variant("s", label),
                        "toggle-type": GLib.Variant("s", "checkmark"),
                        "toggle-state": GLib.Variant("i", 1 if is_selected else 0),
                    },
                    parent=ID_PROFILE_HEADER,
                )
        else:
            add(
                ID_PROFILE_HEADER,
                {
                    "label": GLib.Variant("s", _("Thermal profile: not supported by this hardware")),
                    "enabled": GLib.Variant("b", False),
                },
            )

        # 51/60..: "Mode de charge" submenu, mirroring the profile one
        # above. Only shown when the firmware actually exposes
        # PrimaryBattChargeCfg (e.g. no dell-wmi-sysman, or a model that
        # doesn't have it) -- same "hide rather than show a dead/greyed-out
        # control" choice the profile section makes via _profile_supported.
        if self._charge_mode_choices:
            add(
                ID_CHARGE_MODE_HEADER,
                {
                    "label": GLib.Variant("s", _("Charging mode")),
                    "children-display": GLib.Variant("s", "submenu"),
                },
            )
            for idx, choice in enumerate(self._charge_mode_choices):
                item_id = ID_CHARGE_MODE_BASE + idx
                is_selected = choice == self._charge_mode
                label = _CHARGE_MODE_LABELS.get(choice, choice)
                add(
                    item_id,
                    {
                        "label": GLib.Variant("s", label),
                        "toggle-type": GLib.Variant("s", "checkmark"),
                        "toggle-state": GLib.Variant("i", 1 if is_selected else 0),
                    },
                    parent=ID_CHARGE_MODE_HEADER,
                )

        # 100: Separator between the submenus and "Open"
        add(ID_SEP_3, {"type": GLib.Variant("s", "separator")})

        # 101: Open window
        add(
            ID_OPEN_APP,
            {
                "label": GLib.Variant("s", _("Open Dell Power Manager")),
                "icon-name": GLib.Variant("s", "io.github.nplacide95.PlatformPower"),
            },
        )

        # No "Quit" item here on purpose: this is a persistent system
        # service (see tests/test_tray.py::test_tray_dbusmenu_properties,
        # which asserts it stays absent), the same way the window's close
        # button only hides it rather than exiting. on_quit is still wired
        # through for callers that manage their own lifecycle (e.g. tests,
        # or a future settings-triggered shutdown), just not exposed here.

        return items, children

    def _get_items(self) -> dict[int, dict[str, GLib.Variant]]:
        items, _children = self._get_tree()
        return items

    def _build_layout(
        self, parent_id: int = 0, recursion_depth: int = -1
    ) -> tuple[int, dict[str, GLib.Variant], list]:
        """Build the (id, properties, children) triple GetLayout expects,
        for `parent_id` down to `recursion_depth` levels (-1 = unlimited,
        matching what every host that doesn't lazily fetch submenus asks
        for). Each entry in `children` is itself a fully-formed
        GLib.Variant of type "(ia{sv}av)", as required for the outer "av"
        (array of variant) slot -- unlike a plain nested Python tuple,
        which is only valid for the single top-level triple GetLayout
        returns, not for entries *inside* an array of variants.
        """
        items, children = self._get_tree()

        def build_children(node_id: int, depth: int) -> list[GLib.Variant]:
            if depth == 0:
                return []
            next_depth = depth if depth < 0 else depth - 1
            return [
                GLib.Variant(
                    "(ia{sv}av)",
                    (child_id, items.get(child_id, {}), build_children(child_id, next_depth)),
                )
                for child_id in children.get(node_id, [])
            ]

        props = (
            items.get(parent_id, {})
            if parent_id != 0
            else {"children-display": GLib.Variant("s", "submenu")}
        )
        return (parent_id, props, build_children(parent_id, recursion_depth))

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
            layout = self._build_layout(parent_id, depth)
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
        elif ID_CHARGE_MODE_BASE <= item_id < ID_CHARGE_MODE_BASE + len(self._charge_mode_choices):
            choice = self._charge_mode_choices[item_id - ID_CHARGE_MODE_BASE]
            if choice != self._charge_mode and self._on_set_charge_mode is not None:
                GLib.idle_add(self._on_set_charge_mode, choice)
        elif item_id == ID_OPEN_APP:
            GLib.idle_add(self._on_open)

    def destroy(self) -> None:
        if self._bus is not None:
            if self._watcher_sub_id:
                self._bus.signal_unsubscribe(self._watcher_sub_id)
                self._watcher_sub_id = None
            if self._watcher_name_id:
                Gio.bus_unwatch_name(self._watcher_name_id)
                self._watcher_name_id = None
            if self._sni_reg_id:
                self._bus.unregister_object(self._sni_reg_id)
                self._sni_reg_id = None
            if self._menu_reg_id:
                self._bus.unregister_object(self._menu_reg_id)
                self._menu_reg_id = None
            self._bus = None
