Name:           platform-power-manager
Version:        0.1.0
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

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       polkit
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
install -Dm644 data/icons/io.github.nplacide95.PlatformPower.png \
    %{buildroot}%{_datadir}/pixmaps/io.github.nplacide95.PlatformPower.png

# AppStream metadata
install -Dm644 data/io.github.nplacide95.PlatformPower.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.nplacide95.PlatformPower.metainfo.xml

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.nplacide95.PlatformPower.desktop
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

%files
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
%{_datadir}/icons/hicolor/*/apps/io.github.nplacide95.PlatformPower.*
%{_datadir}/pixmaps/io.github.nplacide95.PlatformPower.png
%{_metainfodir}/io.github.nplacide95.PlatformPower.metainfo.xml

%changelog
* Fri Sep 19 2025 Platform Power packaging <noreply@example.invalid> - 0.1.0-1
- Initial packaging: thermal profile, battery charge thresholds,
  and dynamically-discovered dell-wmi-sysman BIOS power attributes
  (Peak Shift, Advanced Charge Configuration, USB-C PowerShare).
