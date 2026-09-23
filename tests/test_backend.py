from __future__ import annotations

import pytest

from platform_power import backend


def test_categorize_allowed_power_attributes():
    assert backend._categorize("PrimaryBattChargeCfg", "Battery Configuration") == "battery_mode"
    assert backend._categorize("PeakShiftCfg", "Enable Peak Shift") == "peak_shift"
    assert backend._categorize("PeakShiftBatteryThreshold", "Battery Threshold [15% to 100%]") == "peak_shift"
    assert backend._categorize("AdvBatteryChargeCfg", "Enable Advanced Battery Charge Configuration") == "advanced_charge"
    assert backend._categorize("CustomChargeStart", "Custom Charge Start") == "advanced_charge"
    assert backend._categorize("ThermalManagement", "Thermal Management") == "thermal"
    assert backend._categorize("UsbPowerShare", "Enable USB PowerShare") == "usb_c"
    assert backend._categorize("TypeCDockOverride", "Type-C Dock Override") == "usb_c"
    assert backend._categorize("PowerOnLidOpen", "Power On Lid Open") == "power_options"
    assert backend._categorize("WakeOnAc", "Wake on AC") == "power_options"
    assert backend._categorize("AutoOn", "Auto On Time") == "auto_on"
    assert backend._categorize("KbdBacklightTimeoutAc", "Keyboard Backlight with AC") == "keyboard_backlight"
    assert backend._categorize("CpuCoreExt", "CPU Core Configuration") == "cpu_performance"


def test_categorize_dangerous_attributes_blacklisted():
    # Dangerous/security/firmware attributes must be rejected (return None)
    assert backend._categorize("reset_bios", "reset_bios") is None
    assert backend._categorize("RemoteWipeInternalDrives", "Remote Wipe Internal Drives") is None
    assert backend._categorize("TpmSecurity", "TPM 2.0 Security On") is None
    assert backend._categorize("SecureBoot", "Secure Boot Enable") is None
    assert backend._categorize("AdminPwd", "Admin Password") is None
    assert backend._categorize("SystemPwd", "System Password") is None
    assert backend._categorize("Camera", "Enable Camera") is None
    assert backend._categorize("Microphone", "Enable Microphone") is None
    assert backend._categorize("FingerprintReader", "Enable Fingerprint Reader") is None
    assert backend._categorize("Virtualization", "Intel Virtualization Technology") is None
    assert backend._categorize("SvcTag", "Service Tag") is None


def test_set_firmware_attribute_rejects_blacklisted(monkeypatch, tmp_path):
    root = tmp_path / "dell-wmi-sysman"
    attrs = root / "attributes" / "reset_bios"
    attrs.mkdir(parents=True)
    (attrs / "current_value").write_text("", encoding="utf-8")
    (attrs / "display_name").write_text("Reset BIOS", encoding="utf-8")

    monkeypatch.setattr(backend, "find_sysman_root", lambda: str(root))

    with pytest.raises(ValueError, match="n'est pas autorisée"):
        backend.set_firmware_attribute("reset_bios", "Reset")


def test_set_firmware_attribute_unknown_or_traversal(monkeypatch, tmp_path):
    root = tmp_path / "dell-wmi-sysman"
    attrs = root / "attributes"
    attrs.mkdir(parents=True)

    # Legitimate attribute
    legit = attrs / "ThermalManagement"
    legit.mkdir()
    (legit / "current_value").write_text("Optimized\n", encoding="utf-8")
    (legit / "display_name").write_text("Thermal Management\n", encoding="utf-8")

    # Directory outside attributes/ that happens to have current_value
    poc_dir = tmp_path / "poc"
    poc_dir.mkdir()
    poc_file = poc_dir / "current_value"
    poc_file.write_text("UNTOUCHED", encoding="utf-8")
    (poc_dir / "display_name").write_text("Thermal Management", encoding="utf-8")

    monkeypatch.setattr(backend, "find_sysman_root", lambda: str(root))

    # Path traversal must raise FileNotFoundError and not modify the file
    with pytest.raises(FileNotFoundError, match="unknown firmware attribute"):
        backend.set_firmware_attribute("../../poc", "HACKED")
    assert poc_file.read_text(encoding="utf-8") == "UNTOUCHED"

    # Non-existent attribute must also raise FileNotFoundError
    with pytest.raises(FileNotFoundError, match="unknown firmware attribute"):
        backend.set_firmware_attribute("NonExistentAttr", "val")


def test_set_charge_thresholds_validation(monkeypatch, tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir(parents=True)
    (bat / "type").write_text("Battery\n", encoding="utf-8")
    (bat / "charge_control_start_threshold").write_text("50", encoding="utf-8")
    (bat / "charge_control_end_threshold").write_text("100", encoding="utf-8")

    monkeypatch.setattr(backend.sysfs, "POWER_SUPPLY_ROOT", str(tmp_path))

    # start >= end must fail
    with pytest.raises(ValueError, match="inférieur"):
        backend.set_charge_thresholds("BAT0", 80, 80)

    with pytest.raises(ValueError, match="inférieur"):
        backend.set_charge_thresholds("BAT0", 90, 80)

    # Valid thresholds should write
    backend.set_charge_thresholds("BAT0", 60, 85)
    assert (bat / "charge_control_start_threshold").read_text(encoding="utf-8") == "60"
    assert (bat / "charge_control_end_threshold").read_text(encoding="utf-8") == "85"


def test_set_charge_thresholds_unknown_or_traversal(monkeypatch, tmp_path):
    power_root = tmp_path / "power_supply"
    power_root.mkdir()
    bat = power_root / "BAT0"
    bat.mkdir()
    (bat / "type").write_text("Battery\n", encoding="utf-8")
    (bat / "charge_control_start_threshold").write_text("50", encoding="utf-8")
    (bat / "charge_control_end_threshold").write_text("100", encoding="utf-8")

    # Target directory outside power_root mimicking a battery
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_start = target_dir / "charge_control_start_threshold"
    target_end = target_dir / "charge_control_end_threshold"
    target_start.write_text("ORIGINAL_START", encoding="utf-8")
    target_end.write_text("ORIGINAL_END", encoding="utf-8")

    monkeypatch.setattr(backend.sysfs, "POWER_SUPPLY_ROOT", str(power_root))

    # Path traversal must raise FileNotFoundError and not modify target files
    with pytest.raises(FileNotFoundError, match="unknown battery"):
        backend.set_charge_thresholds("../target", 60, 80)
    assert target_start.read_text(encoding="utf-8") == "ORIGINAL_START"
    assert target_end.read_text(encoding="utf-8") == "ORIGINAL_END"

    with pytest.raises(FileNotFoundError, match="unknown battery"):
        backend.set_charge_thresholds("../../../etc", 60, 80)

    with pytest.raises(FileNotFoundError, match="unknown battery"):
        backend.set_charge_thresholds("BAT99", 60, 80)

    # Non-battery device (e.g. AC adapter) must also be rejected
    ac = power_root / "AC"
    ac.mkdir()
    (ac / "type").write_text("Mains\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="unknown battery"):
        backend.set_charge_thresholds("AC", 60, 80)


def test_set_platform_profile_validation(monkeypatch, tmp_path):
    profile_path = tmp_path / "platform_profile"
    choices_path = tmp_path / "platform_profile_choices"
    profile_path.write_text("balanced\n", encoding="utf-8")
    choices_path.write_text("cool quiet balanced performance\n", encoding="utf-8")

    monkeypatch.setattr(backend.sysfs, "PLATFORM_PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(backend.sysfs, "PLATFORM_PROFILE_CHOICES_PATH", str(choices_path))

    with pytest.raises(ValueError, match="not one of"):
        backend.set_platform_profile("ultra-hyper-mode")

    backend.set_platform_profile("performance")
    assert profile_path.read_text(encoding="utf-8") == "performance"


def test_set_battery_charge_mode(monkeypatch, tmp_path):
    root = tmp_path / "dell-wmi-sysman"
    cfg = root / "attributes" / "PrimaryBattChargeCfg"
    cfg.mkdir(parents=True)
    val_file = cfg / "current_value"
    val_file.write_text("Adaptive\n", encoding="utf-8")
    (cfg / "possible_values").write_text("Adaptive;Standard;Express;PrimAcUse;Custom", encoding="utf-8")

    monkeypatch.setattr(backend, "find_sysman_root", lambda: str(root))

    backend.set_battery_charge_mode("Express")
    assert val_file.read_text(encoding="utf-8") == "Express"

    with pytest.raises(ValueError, match="not one of"):
        backend.set_battery_charge_mode("NonExistentMode")


def test_firmware_page_mappings():
    from platform_power.pages.firmware import (
        _CATEGORY_ORDER,
        _resolve_category,
        _get_attr_info,
        _VALUE_TRANSLATIONS,
    )

    assert len(_CATEGORY_ORDER) == 10
    assert _CATEGORY_ORDER[0] == "battery_mode"
    assert _CATEGORY_ORDER[1] == "advanced_charge"
    assert _CATEGORY_ORDER[2] == "peak_shift"
    assert _CATEGORY_ORDER[3] == "thermal"
    assert _CATEGORY_ORDER[4] == "auto_on"

    # Category resolution
    assert _resolve_category({"id": "AutoOnHr"}) == "auto_on"
    assert _resolve_category({"id": "KbdBacklightTimeoutAc"}) == "keyboard_backlight"
    assert _resolve_category({"id": "CpuCoreExt"}) == "cpu_performance"
    assert _resolve_category({"id": "UnknownAttr", "category": "power_options"}) == "power_options"
    assert _resolve_category({"id": "TotallyUnknown", "category": "foo"}) == "other"

    # Metadata & french translations
    title, subtitle = _get_attr_info({"id": "AutoOnHr"})
    assert "Heure" in title
    assert len(subtitle) > 0

    assert _VALUE_TRANSLATIONS["Disabled"] == "Désactivé"
    assert _VALUE_TRANSLATIONS["Enabled"] == "Activé"
    assert _VALUE_TRANSLATIONS["UltraPerformance"] == "Performances maximales"


