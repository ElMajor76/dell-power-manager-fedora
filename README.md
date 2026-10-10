# Dell Power Manager for Linux (Fedora and Ubuntu) Dell laptops

> **Ubuntu 24.04 LTS or newer is supported** since 0.5.0 — see
> [`docs/UBUNTU.md`](docs/UBUNTU.md) (install, hardware checks, troubleshooting,
> what has been tested). Every change to the project is tracked in
> [`CHANGELOG.md`](CHANGELOG.md).

GTK4/libadwaita app + privileged D-Bus daemon that brings the same
*category* of settings as Dell Command | Power Manager (Windows) to
Fedora/Ubuntu GNOME/KDE: thermal/performance profile, battery charge-threshold
management, and — where the firmware supports it — BIOS-level extras
like Peak Shift, scheduled/advanced battery charging, and USB-C
PowerShare. Also includes a system tray indicator with quick profile
switching.

The project's internal codename is still `platform-power` (package,
binaries, D-Bus name), which you'll see throughout this repo and the
source tree.

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

This has been validated end-to-end on a real Dell laptop running Fedora
(daemon running as a systemd service, polkit prompts, and sysfs writes
all exercised against actual hardware), but firmware attribute names
still vary by model and BIOS revision. Two things follow from that:

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
`src/platform_power/dbus_iface.xml` for the D-Bus contract. Every
identifier that reaches a sysfs path from a D-Bus caller (battery name,
firmware attribute id) is validated against the real, discovered list
(`list_batteries()` / `sysfs.list_dir(...)`) before the path is built,
to rule out directory-traversal payloads reaching an unexpected file.

## Installation rapide (RPM pré-compilé)

Le paquet RPM le plus récent est joint aux
[releases GitHub](https://github.com/ElMajor76/dell-power-manager-fedora/releases)
et se trouve aussi dans le dossier `packages/` du dépôt :

```bash
sudo dnf install packages/platform-power-manager-0.3.0-1.fc44.noarch.rpm
```

## Building the RPM

Sur Fedora :

```bash
sudo dnf install rpmdevtools python3-gobject gtk4-devel libadwaita-devel desktop-file-utils libappstream-glib libgudev
rpmdev-setuptree

# from the project root (this directory)
VERSION=0.3.0
tar --transform "s,^,platform-power-manager-$VERSION/," \
    -czf ~/rpmbuild/SOURCES/platform-power-manager-$VERSION.tar.gz \
    src bin data LICENSE README.md

cp platform-power-manager.spec ~/rpmbuild/SPECS/
rpmbuild -ba ~/rpmbuild/SPECS/platform-power-manager.spec
```

The built RPM lands in `~/rpmbuild/RPMS/noarch/`. Install it with:

```bash
sudo dnf install ~/rpmbuild/RPMS/noarch/platform-power-manager-$VERSION*.noarch.rpm
```

`dnf` will pull in `python3-gobject`, `gtk4`, `libadwaita`, `polkit`, and
`libgudev` as runtime dependencies automatically.

## Other distributions

Fedora/RHEL is the primary target, but the app itself has nothing
Fedora-specific in it (plain Python + GTK4/libadwaita/polkit/systemd/D-Bus),
so it's packaged for a few others too. Each was built and installed in a
real container of the target distribution before being committed here, not
just written by inspection.

### Debian / Ubuntu (.deb)

Ubuntu 24.04 LTS or newer (needs libadwaita ≥ 1.5 and GTK ≥ 4.10). Full
guide: [`docs/UBUNTU.md`](docs/UBUNTU.md).

```bash
sudo apt install ./packages/platform-power-manager_0.5.0-1_all.deb
```

Building from source (also runs the test suite):

```bash
sudo apt install build-essential debhelper dh-python devscripts fakeroot \
    gettext dbus python3-gi python3-pytest gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-gudev-1.0 gir1.2-gdkpixbuf-2.0
dpkg-buildpackage -us -uc -b
sudo apt install ../platform-power-manager_*_all.deb
```

The prebuilt `.deb` is also attached to the
[GitHub release](https://github.com/ElMajor76/dell-power-manager-fedora/releases).
Packaging lives in `debian/` at the repository root (a "native" package,
`debian/source/format` = `3.0 (native)`).

### Arch Linux (PKGBUILD)

```bash
cd packaging/archlinux
makepkg -si
```

`packaging/archlinux/PKGBUILD` (0.5.0; refresh the checksum with
`packaging/archlinux/update-sha256.sh` after each new tag; not yet
build-tested on a real Arch system) pulls the source from this repo's GitHub
release tarball rather than the working tree. The daemon and its D-Bus
service file are installed under `/usr/lib/platform-power-manager/` instead
of `/usr/libexec/` (not a standard directory on Arch), with the `ExecStart=`
paths patched at package time to match.

### openSUSE (RPM)

```bash
cd packaging/opensuse
sudo zypper install rpm-build python3-devel systemd-rpm-macros desktop-file-utils appstream-glib
rpmbuild --define "_topdir $HOME/rpmbuild" -bb platform-power-manager.spec
sudo zypper install ~/rpmbuild/RPMS/noarch/platform-power-manager-$VERSION*.noarch.rpm
```

Otherwise near-identical to the Fedora spec (same RPM macros throughout),
except openSUSE splits each GObject-Introspection typelib into its own
package separate from the runtime library it introspects, so the
dependency list names the typelibs explicitly
(`typelib-1_0-{Gtk-4_0,Adw-1,GUdev-1_0,GdkPixbuf-2_0}`) instead of the
generic `gtk4`/`libadwaita`/`libgudev` capability names that resolve fine
on Fedora.

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

## Releases

Tagged releases (with pre-built RPMs attached) are published on the
[GitHub Releases page](https://github.com/ElMajor76/dell-power-manager-fedora/releases).
See [`CHANGELOG.md`](CHANGELOG.md) for the complete, version-by-version
history (the packaging-specific logs are `debian/changelog` and the `%changelog`
of the two RPM specs).

## Tests

```bash
sudo apt install python3-gi python3-pytest gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-gudev-1.0 gir1.2-gdkpixbuf-2.0 dbus xvfb   # Ubuntu/Debian
PYTHONPATH=src dbus-run-session -- /usr/bin/python3 -m pytest tests -q
PYTHONPATH=src dbus-run-session -- xvfb-run -a /usr/bin/python3 tests/smoke_gui.py
```

The same checks (plus `.deb` build and `lintian`) run in CI on Ubuntu 24.04
(`.github/workflows/ci.yml`).

