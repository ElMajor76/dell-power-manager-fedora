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


def test_set_charge_thresholds_validation(monkeypatch, tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir(parents=True)
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

