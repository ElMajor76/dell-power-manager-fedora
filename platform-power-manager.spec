Name:           platform-power-manager
Version:        0.4.0
Release:        1%{?dist}
Summary:        Thermal profile, battery charging and BIOS power settings, GNOME/KDE GUI

License:        MIT
URL:            https://github.com/nplacide95/dell-power-manager-fedora
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
BuildRequires:  gettext

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       polkit
Requires:       libgudev
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd

%description
Platform Power is a GTK4/libadwaita application and privileged D-Bus
daemon that expose, on Fedora, the same category of settings Dell
Command | Power Manager exposes on Windows: ACPI thermal/performance
profile, battery charge-threshold management, and (on machines whose
firmware supports it, via the dell-wmi-sysman kernel driver) BIOS-level
extras such as Peak Shift, Advanced/scheduled battery charging and
USB-C PowerShare.

It is an independent, original implementation built on top of standard
Linux kernel interfaces (ACPI platform_profile, the power_supply class,
and firmware-attributes) and is not affiliated with or endorsed by
Dell Technologies. Which advanced settings are available depends
entirely on your machine's BIOS/firmware and kernel version.

%prep
%autosetup -p1

%build
# Pure Python + data files; nothing to compile.

%install
# Python package
install -d %{buildroot}%{python3_sitelib}/platform_power
cp -pr src/platform_power/. %{buildroot}%{python3_sitelib}/platform_power/
find %{buildroot}%{python3_sitelib}/platform_power -name '__pycache__' -exec rm -rf {} +

# Executables
install -Dm755 bin/platform-power %{buildroot}%{_bindir}/platform-power
install -Dm755 bin/platform-power-daemon %{buildroot}%{_libexecdir}/platform-power-daemon

# systemd unit
install -Dm644 data/systemd/platform-power-daemon.service \
    %{buildroot}%{_unitdir}/platform-power-daemon.service

# D-Bus system service activation + policy
install -Dm644 data/dbus/io.github.nplacide95.PlatformPower.Daemon1.service \
    %{buildroot}%{_datadir}/dbus-1/system-services/io.github.nplacide95.PlatformPower.Daemon1.service
install -Dm644 data/dbus/io.github.nplacide95.PlatformPower.Daemon1.conf \
    %{buildroot}%{_sysconfdir}/dbus-1/system.d/io.github.nplacide95.PlatformPower.Daemon1.conf

# polkit policy
install -Dm644 data/polkit/io.github.nplacide95.PlatformPower.policy \
    %{buildroot}%{_datadir}/polkit-1/actions/io.github.nplacide95.PlatformPower.policy

# desktop entry + icon
install -Dm644 data/io.github.nplacide95.PlatformPower.desktop \
    %{buildroot}%{_datadir}/applications/io.github.nplacide95.PlatformPower.desktop
install -Dm644 data/icons/io.github.nplacide95.PlatformPower.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.nplacide95.PlatformPower.svg
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_256.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_128.png \
    %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_64.png \
    %{buildroot}%{_datadir}/icons/hicolor/64x64/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_48.png \
    %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_32.png \
    %{buildroot}%{_datadir}/icons/hicolor/32x32/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_24.png \
    %{buildroot}%{_datadir}/icons/hicolor/24x24/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_22.png \
    %{buildroot}%{_datadir}/icons/hicolor/22x22/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower_16.png \
    %{buildroot}%{_datadir}/icons/hicolor/16x16/apps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/io.github.nplacide95.PlatformPower.png \
    %{buildroot}%{_datadir}/pixmaps/io.github.nplacide95.PlatformPower.png
install -Dm644 data/icons/temperature-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/status/temperature-symbolic.svg

# AppStream metadata
install -Dm644 data/io.github.nplacide95.PlatformPower.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.nplacide95.PlatformPower.metainfo.xml

# autostart on session login (minimized)
install -Dm644 data/io.github.nplacide95.PlatformPower.autostart.desktop \
    %{buildroot}%{_sysconfdir}/xdg/autostart/io.github.nplacide95.PlatformPower.desktop

# Translations. English is the in-source language; po/fr.po is the only
# translation for now. %find_lang below (and -f %{name}.lang in %files)
# picks up whichever locales actually got compiled here automatically, so
# adding another po/<lang>.po later needs no spec change.
msgfmt -c po/fr.po -o po/fr.mo
install -Dm644 po/fr.mo %{buildroot}%{_datadir}/locale/fr/LC_MESSAGES/%{name}.mo
%find_lang %{name}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.nplacide95.PlatformPower.desktop
desktop-file-validate %{buildroot}%{_sysconfdir}/xdg/autostart/io.github.nplacide95.PlatformPower.desktop
appstream-util validate-relax --nonet \
    %{buildroot}%{_metainfodir}/io.github.nplacide95.PlatformPower.metainfo.xml

%post
%systemd_post platform-power-daemon.service
glib-compile-schemas %{_datadir}/glib-2.0/schemas &>/dev/null || :
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%preun
%systemd_preun platform-power-daemon.service

%postun
%systemd_postun_with_restart platform-power-daemon.service
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files -f %{name}.lang
%license LICENSE
%doc README.md
%{python3_sitelib}/platform_power/
%{_bindir}/platform-power
%{_libexecdir}/platform-power-daemon
%{_unitdir}/platform-power-daemon.service
%{_datadir}/dbus-1/system-services/io.github.nplacide95.PlatformPower.Daemon1.service
%{_sysconfdir}/dbus-1/system.d/io.github.nplacide95.PlatformPower.Daemon1.conf
%{_datadir}/polkit-1/actions/io.github.nplacide95.PlatformPower.policy
%{_datadir}/applications/io.github.nplacide95.PlatformPower.desktop
%{_sysconfdir}/xdg/autostart/io.github.nplacide95.PlatformPower.desktop
%{_datadir}/icons/hicolor/*/apps/io.github.nplacide95.PlatformPower.*
%{_datadir}/icons/hicolor/*/status/temperature-symbolic.svg
%{_datadir}/pixmaps/io.github.nplacide95.PlatformPower.png
%{_metainfodir}/io.github.nplacide95.PlatformPower.metainfo.xml

%changelog
* Sun Sep 27 2026 Platform Power packaging <noreply@example.invalid> - 0.4.0-1
- i18n: the source code's UI strings are now in English (readable by any
  contributor); French is preserved as a full gettext translation
  (po/fr.po, 203 strings) and keeps displaying automatically on a
  French-locale system, matching the previous French-only behaviour.
- Fix: three menu section titles ("Power, lid & wake", "USB-C & docks",
  "Performance & CPU") contained a raw "&", which Adw.PreferencesGroup
  interprets as Pango markup and silently failed to render. Reworded
  using "and" instead of escaping, in both languages.
- Fix: the polkit policy file had no xml:lang markers at all, so its
  three actions always showed in French to every user regardless of
  their system locale. Now has English defaults with xml:lang="fr"
  overrides, matching standard polkit i18n convention.

* Sun Sep 27 2026 Platform Power packaging <noreply@example.invalid> - 0.3.0-1
- Security: harden the systemd unit (PrivateTmp, RestrictAddressFamilies=AF_UNIX,
  RestrictNamespaces, LockPersonality, MemoryDenyWriteExecute, SystemCallFilter).
- Security: document sysfs.py's no-validation-by-design trust boundary so a future
  D-Bus method doesn't skip whitelisting the way backend.py's setters do.
- Fix: set_charge_thresholds() now validates against the firmware's own min/max
  (CustomChargeStart/CustomChargeStop) before writing anything. It previously only
  checked the generic 0-100 kernel range, so an out-of-firmware-range request
  silently reverted with no error reported anywhere. The Custom threshold sliders
  in the GUI now read these bounds live instead of a hardcoded 50-95/55-100.
- Fix: DaemonClient.watch_state_changed() supported only a single callback slot;
  app.py (tray) and window.py (window) both register on the same shared client,
  so the window's registration silently discarded the tray's. The tray never saw
  another StateChanged update past app startup -- e.g. the profile checkmark
  stayed stuck after switching profile from the tray menu. Now a list.
- Tray: thermal profile and charge mode choices are now real flyout submenus
  instead of a flat list under a disabled header.
- Tray: emit ItemsPropertiesUpdated (not just LayoutUpdated) so a checkmark
  actually flips live while its submenu is open, instead of only refreshing on
  next open/close.
- Tray: show battery percentage/status directly in the menu; add a charge-mode
  submenu mirroring the thermal profile one.
- Window: add a primary (hamburger) menu button to the header bar with
  Rafraîchir l'état, Diagnostics (daemon/D-Bus/dell-wmi-sysman status),
  Raccourcis clavier, Documentation and Signaler un problème links, and a
  native Adw.AboutDialog.

* Wed Sep 23 2026 Platform Power packaging <noreply@example.invalid> - 0.2.0-5
- Security fix: validate battery name against list_batteries() in set_charge_thresholds() to prevent sysfs path traversal.
- Security fix: validate attribute_id against sysfs.list_dir() in set_firmware_attribute() to prevent sysfs path traversal.

* Wed Sep 23 2026 Platform Power packaging <noreply@example.invalid> - 0.2.0-4
- Reorganize BIOS Advanced categories into logical, user-friendly groups (battery, charging, peak shift, thermal, auto on, power options, USB-C, keyboard backlight, CPU performance).
- Localize BIOS Advanced tab to French: friendly titles, descriptive subtitles, and translated enum values.
- Maintain full integrity with underlying dell-wmi-sysman sysfs write tokens.

* Wed Sep 23 2026 Platform Power packaging <noreply@example.invalid> - 0.2.0-3
- Autostart on desktop session login via /etc/xdg/autostart/ with --minimized.
- Remove Quitter option from system tray menu so application behaves as a persistent system component.
- Always hide window on close request or shortcuts rather than terminating.

* Wed Sep 23 2026 Platform Power packaging <noreply@example.invalid> - 0.2.0-2
- Fix system tray StatusNotifierItem icon: unset IconThemePath to use standard theme search path.
- Add IconPixmap support for reliable app icon rendering across desktop environments.
- Install native 16x16, 22x22, and 24x24 app icons.

* Tue Sep 22 2026 Platform Power packaging <noreply@example.invalid> - 0.2.0-1
- Security hardening: whitelist safe dell-wmi-sysman BIOS attributes and blacklist dangerous settings.
- Direct Dell native charge modes integration (Adaptive, Express, Standard, Primarily AC, Custom).
- Real-time uevent / sysfs change monitoring via libgudev and Gio.FileMonitor.
- Asynchronous non-blocking D-Bus client calls preventing GUI freezes during Polkit auth.
- Polkit system-bus-name subject hardening to prevent PID race conditions.
- System tray StatusNotifierItem icon theme path and Wayland improvements.

* Fri Sep 19 2025 Platform Power packaging <noreply@example.invalid> - 0.1.0-1
- Initial packaging: thermal profile, battery charge thresholds,
  and dynamically-discovered dell-wmi-sysman BIOS power attributes
  (Peak Shift, Advanced Charge Configuration, USB-C PowerShare).
