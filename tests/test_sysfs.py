from __future__ import annotations

import os

from platform_power import sysfs


def test_read_str_existing(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("  hello world  \n", encoding="utf-8")
    assert sysfs.read_str(str(f)) == "hello world"


def test_read_str_missing():
    assert sysfs.read_str("/path/that/does/not/exist") is None


def test_read_int_valid(tmp_path):
    f = tmp_path / "int.txt"
    f.write_text("42\n", encoding="utf-8")
    assert sysfs.read_int(str(f)) == 42


def test_read_int_invalid(tmp_path):
    f = tmp_path / "invalid.txt"
    f.write_text("not_a_number\n", encoding="utf-8")
    assert sysfs.read_int(str(f)) is None


def test_write_str(tmp_path):
    f = tmp_path / "output.txt"
    sysfs.write_str(str(f), "cool")
    assert f.read_text(encoding="utf-8") == "cool"


def test_list_dir(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    assert sysfs.list_dir(str(tmp_path)) == ["a", "b"]
    assert sysfs.list_dir("/path/does/not/exist") == []
