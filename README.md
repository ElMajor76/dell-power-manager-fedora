# Platform Power

GTK4/libadwaita app + privileged D-Bus daemon that brings the same
*category* of settings as Dell Command | Power Manager (Windows) to
Fedora GNOME/KDE: thermal/performance profile, battery charge-threshold
management, and — where the firmware supports it — BIOS-level extras
like Peak Shift, scheduled/advanced battery charging, and USB-C
PowerShare.

**This is an independent, original implementation, not a port or a
decompilation of Dell's Windows software.** It is not affiliated with
or endorsed by Dell Technologies, and does not use the "Dell" name,
logo, or any of Dell's Windows-side code. It works entirely through
standard upstream Linux kernel interfaces:

| Feature (Windows: Dell Power Manager) | Linux kernel interface used |
|---|---|
| Thermal Management slider | `/sys/firmware/acpi/platform_profile` (`ACPI platform_profile`, kernel ≥ 5.14; same thing GNOME/KDE's own power-mode switcher uses) |
| Battery Information | `/sys/class/power_supply/BAT0/*` (capacity, status, cycle count, energy_full vs energy_full_design for health %) |
| Custom / Primarily AC use / Express Charge | `/sys/class/power_supply/BAT0/charge_control_{start,end}_threshold` (via the in-tree `dell-laptop` driver) |
| Peak Shift, Advanced Battery Charge Configuration, USB-C PowerShare, and anything else in Dell's BIOS setup | `/sys/class/firmware-attributes/dell-wmi-sysman/attributes/*` (in-tree `dell-wmi-sysman` driver, present on Latitude/Precision/OptiPlex business machines) |

## Important: hardware/firmware compatibility

This was built and packaged from a Windows machine (no Fedora available
to test against at build time), so **it has not been run against real
hardware yet.** Two things follow from that:

1. **`platform_profile` and battery thresholds** are well-documented,
   stable kernel ABIs — these should work as described on any recent
   Fedora kernel where the relevant driver (`dell-laptop`,
   `dell_smbios`) loads for your model.
2. **The "BIOS avancé" page is fully dynamic on purpose.** Dell does not
   publish a stable list of BIOS attribute names across firmware
   revisions, so instead of hard-coding guessed attribute IDs for Peak
   Shift / Advanced Charge / USB-C PowerShare (which could easily be
   wrong for your exact BIOS version and silently do nothing, or worse,
   write to the wrong attribute), the app reads whatever
   `/sys/class/firmware-attributes/dell-wmi-sysman/attributes/` actually
   exposes at runtime and sorts it into the right category by matching
   on the attribute's own `display_name`. Anything it doesn't recognise
   still shows up under "Autres réglages d'alimentation du BIOS" instead
   of being hidden.

Before installing, check on the target machine (as a normal user, no
root needed) what's actually available:

```bash
cat /sys/firmware/acpi/platform_profile /sys/firmware/acpi/platform_profile_choices
ls /sys/class/power_supply/BAT0/ | grep charge_control
ls /sys/class/firmware-attributes/ 2>/dev/null
```

If the last command shows nothing, `dell-wmi-sysman` isn't loaded for
this model/BIOS — the "BIOS avancé" page will say so explicitly rather
than pretending those features exist.

If a **BIOS admin password** is set on the machine, `dell-wmi-sysman`
will refuse writes to protected attributes; the app detects this
(`authentication/Admin/is_enabled`) and shows a banner instead of
failing silently. This tool deliberately does not attempt to enter a
BIOS admin password on your behalf.

## Architecture

- `platform-power-daemon` — runs as **root**, D-Bus-activated on the
  **system bus** as `io.github.nplacide95.PlatformPower.Daemon1`. Owns
  every sysfs write. `GetState` is unauthenticated (read-only);
  `SetPlatformProfile` / `SetChargeThresholds` are gated by polkit with
  `allow_active=yes` (no password prompt for the locally logged-in
  user, matching how GNOME/KDE's own power-mode switch behaves);
  `SetFirmwareAttribute` requires `auth_admin_keep` (password prompt),
  since it writes into actual BIOS setup variables.
- `platform-power` — the GTK4/libadwaita GUI and system tray indicator, runs as the
  normal user, talks to the daemon exclusively over D-Bus. Never touches sysfs or
  needs any elevated privilege itself. Integrates a StatusNotifierItem / DBusMenu
  tray icon (GNOME via AppIndicator, KDE, XFCE, Waybar) with quick thermal profile
  switching directly from the tray, mouse wheel profile cycling, battery status in
  the tooltip, close-to-tray, and a `--minimized` / `-m` command-line option.

See `src/platform_power/backend.py` for the sysfs logic and
`src/platform_power/dbus_iface.xml` for the D-Bus contract.

## Installation rapide (RPM pré-compilé)

Un paquet RPM prêt à l'emploi est directement disponible dans le dossier `packages/` du dépôt :

```bash
sudo dnf install packages/platform-power-manager-0.2.0-1.fc44.noarch.rpm
```

## Building the RPM

Sur Fedora :

```bash
sudo dnf install rpmdevtools python3-gobject gtk4-devel libadwaita-devel desktop-file-utils libappstream-glib libgudev
rpmdev-setuptree

# from the project root (this directory)
VERSION=0.2.0
tar --transform "s,^,platform-power-manager-$VERSION/," \
    -czf ~/rpmbuild/SOURCES/platform-power-manager-$VERSION.tar.gz \
    src bin data LICENSE README.md

cp platform-power-manager.spec ~/rpmbuild/SPECS/
rpmbuild -ba ~/rpmbuild/SPECS/platform-power-manager.spec
```

The built RPM lands in `~/rpmbuild/RPMS/noarch/`. Install it with:

```bash
sudo dnf install ~/rpmbuild/RPMS/noarch/platform-power-manager-0.2.0-1*.noarch.rpm
```

`dnf` will pull in `python3-gobject`, `gtk4`, `libadwaita`, `polkit`, and
`libgudev` as runtime dependencies automatically.

## Running / troubleshooting

The daemon is D-Bus-activated, so you don't need to `systemctl start`
it manually — launching the app (or running `busctl call
io.github.nplacide95.PlatformPower.Daemon1 ...`) starts it on demand.
Useful commands:

```bash
systemctl status platform-power-daemon.service
journalctl -u platform-power-daemon.service -e
busctl --system introspect io.github.nplacide95.PlatformPower.Daemon1 \
    /io/github/nplacide95/PlatformPower/Daemon1
```

If the app shows "Service indisponible", the most common causes are:
the RPM's `%post` D-Bus/polkit files not being picked up without a
`systemctl daemon-reload` (handled by the `%systemd_post` macro, but
worth checking), or SELinux denials — check `journalctl -u
platform-power-daemon` and `ausearch -m avc -ts recent` if so.

## Known limitations

- No automated way to enter a BIOS admin password — attributes behind
  one are shown read-only-in-practice with a warning banner.
- Multi-battery systems (e.g. behind certain docks) only manage the
  first battery reported under `/sys/class/power_supply/`, same as
  Dell's own tool.
- Not submitted to Fedora's official repositories; this is a
  self-built/self-signed RPM for personal use unless you choose to
  package it properly for COPR or Fedora review later.

