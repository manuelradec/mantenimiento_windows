"""Tests for services.drivers.backup_drivers (M5, Phase A).

Covers:
- _resolve_backup_dest rejects unsafe paths.
- backup_drivers creates a timestamped subdir and invokes pnputil.
- Parsing of pnputil output for exported count.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import drivers as drv
from services.command_runner import CommandResult, CommandStatus


class TestResolveBackupDest:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            None,
            r"\\server\share\drivers",
            r"drivers",
            r".\drivers",
            r"C:\foo\..\bar",
        ],
    )
    def test_rejects_unsafe(self, bad):
        with pytest.raises(ValueError):
            drv._resolve_backup_dest(bad)

    @pytest.mark.parametrize(
        "good",
        [
            r"C:\backup\drivers",
            r"D:\export",
        ],
    )
    def test_accepts_local(self, good):
        result = drv._resolve_backup_dest(good)
        assert result.startswith(good[0:2])


class TestBackupDrivers:
    def test_error_on_bad_dest(self):
        r = drv.backup_drivers("")
        assert r.status == CommandStatus.ERROR

    def test_creates_timestamped_dir_and_calls_pnputil(self, tmp_path, monkeypatch):
        # Drive letter required by validation: simulate by mocking _resolve_backup_dest.
        base = str(tmp_path)
        monkeypatch.setattr(drv, "_resolve_backup_dest", lambda p: base)
        called = {}

        def fake_run_cmd(cmd, timeout=None, requires_admin=False, description=""):
            called["cmd"] = cmd
            return CommandResult(
                status=CommandStatus.SUCCESS,
                output="Microsoft PnP Utility\n\n7 driver package(s) exported successfully.",
                return_code=0,
            )

        monkeypatch.setattr(drv, "run_cmd", fake_run_cmd)

        r = drv.backup_drivers(r"C:\backup\drivers")
        assert r.status == CommandStatus.SUCCESS
        # pnputil command was invoked with /export-driver
        assert "/export-driver" in called["cmd"]
        # target_dir surfaced in details, prefixed with drivers_backup_
        target_dir = r.details["target_dir"]
        assert "drivers_backup_" in target_dir
        assert os.path.isdir(target_dir)
        # exported_count parsed from output text
        assert r.details["exported_count"] == 7

    def test_pnputil_failure_propagates_status(self, tmp_path, monkeypatch):
        base = str(tmp_path)
        monkeypatch.setattr(drv, "_resolve_backup_dest", lambda p: base)

        def fake_run_cmd(cmd, timeout=None, requires_admin=False, description=""):
            return CommandResult(
                status=CommandStatus.REQUIRES_ADMIN,
                output="",
                error="Requires admin",
                return_code=5,
            )

        monkeypatch.setattr(drv, "run_cmd", fake_run_cmd)
        r = drv.backup_drivers(r"C:\backup\drivers")
        assert r.status == CommandStatus.REQUIRES_ADMIN
