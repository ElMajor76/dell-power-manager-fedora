"""Guards against the version/packaging drift that the project used to
handle by hand (see the comment above APP_VERSION in app.py)."""

from __future__ import annotations

import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, f"pattern {pattern!r} not found"
    return match.group(1)


def test_versions_are_consistent():
    app = _first(r'^APP_VERSION = "([^"]+)"', _read("src", "platform_power", "app.py"))
    window = _first(r'^_VERSION = "([^"]+)"', _read("src", "platform_power", "window.py"))
    metainfo = _first(r'<release version="([^"]+)"', _read("data", "io.github.nplacide95.PlatformPower.metainfo.xml"))
    fedora = _first(r"^Version:\s+(\S+)", _read("platform-power-manager.spec"))
    suse = _first(r"^Version:\s+(\S+)", _read("packaging", "opensuse", "platform-power-manager.spec"))
    debian = _first(r"^platform-power-manager \(([^-)]+)-\d+\)", _read("debian", "changelog"))
    arch = _first(r"^pkgver=(\S+)", _read("packaging", "archlinux", "PKGBUILD"))
    changelog = _first(r"^## \[([^\]]+)\]", _read("CHANGELOG.md"))
    assert {app, window, metainfo, fedora, suse, debian, arch, changelog} == {app}


def test_arch_pkgbuild_installs_files_that_exist():
    pkgbuild = _read("packaging", "archlinux", "PKGBUILD")
    for rel in re.findall(r"install -Dm\d+ ((?:data|bin|debian)/[^\s\\]+)", pkgbuild):
        assert os.path.exists(os.path.join(ROOT, rel)), rel
    assert "/usr/share/dbus-1/system.d/" in pkgbuild
    assert "/etc/dbus-1" not in pkgbuild


def test_debian_unit_is_the_shared_unit():
    # A symlink (not a copy) so the Ubuntu unit can never drift from data/systemd.
    path = os.path.join(ROOT, "debian", "platform-power-manager.platform-power-daemon.service")
    assert os.path.islink(path)
    assert os.path.realpath(path) == os.path.join(ROOT, "data", "systemd", "platform-power-daemon.service")


def test_debian_ships_dbus_policy_under_usr_share():
    rules = _read("debian", "rules")
    assert "/usr/share/dbus-1/system.d/" in rules
    assert "/etc/dbus-1/system.d" not in rules


def test_polkit_policy_is_valid_xml_and_matches_daemon_actions():
    import xml.etree.ElementTree as ET

    tree = ET.parse(os.path.join(ROOT, "data", "polkit", "io.github.nplacide95.PlatformPower.policy"))
    declared = {a.get("id") for a in tree.getroot().findall("action")}
    daemon = _read("src", "platform_power", "daemon.py")
    used = set(re.findall(r'\{_ACTION_PREFIX\}\.([a-z-]+)"', daemon))
    prefix = _first(r'^_ACTION_PREFIX = "([^"]+)"', daemon)
    assert used
    assert {f"{prefix}.{u}" for u in used} <= declared


def test_xml_data_files_are_well_formed():
    import xml.etree.ElementTree as ET

    for rel in (
        ("data", "dbus", "io.github.nplacide95.PlatformPower.Daemon1.conf"),
        ("data", "io.github.nplacide95.PlatformPower.metainfo.xml"),
        ("src", "platform_power", "dbus_iface.xml"),
    ):
        ET.parse(os.path.join(ROOT, *rel))


def test_french_catalog_compiles():
    import shutil

    if shutil.which("msgfmt") is None:
        import pytest

        pytest.skip("msgfmt not installed")
    result = subprocess.run(
        ["msgfmt", "-c", "-o", os.devnull, os.path.join(ROOT, "po", "fr.po")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
