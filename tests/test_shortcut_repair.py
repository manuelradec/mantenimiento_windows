"""Tests for services.shortcut_repair (M1, Phase A).

Covers:
- Input validation in delete_broken_shortcuts (empty list, oversize batch,
  non-.lnk paths).
- Parsing of PowerShell scan output (success path, empty list, single-item
  collapsed by ConvertTo-Json).
- delete_broken_shortcuts counts deleted vs skipped from PowerShell results.
"""

import json
import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import shortcut_repair as svc
from services.command_runner import CommandResult, CommandStatus

# ============================================================
# scan_broken_shortcuts
# ============================================================


class TestScanBrokenShortcuts:
    def test_parses_normal_payload(self, monkeypatch):
        sample = {
            "broken_count": 2,
            "broken": [
                {
                    "location": "user_desktop",
                    "lnk_path": r"C:\Users\u\Desktop\old.lnk",
                    "lnk_name": "old.lnk",
                    "target": r"C:\removed.exe",
                    "arguments": "",
                },
                {
                    "location": "common_startmenu",
                    "lnk_path": r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\gone.lnk",
                    "lnk_name": "gone.lnk",
                    "target": r"C:\gone.exe",
                    "arguments": "",
                },
            ],
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(sample),
            ),
        )
        r = svc.scan_broken_shortcuts()
        assert r.status == CommandStatus.SUCCESS
        assert r.details["broken_count"] == 2
        assert len(r.details["broken"]) == 2

    def test_handles_single_item_collapsed_to_dict(self, monkeypatch):
        sample = {
            "broken_count": 1,
            "broken": {
                "location": "user_desktop",
                "lnk_path": r"C:\Users\u\Desktop\a.lnk",
                "lnk_name": "a.lnk",
                "target": r"C:\nope",
                "arguments": "",
            },
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(sample),
            ),
        )
        r = svc.scan_broken_shortcuts()
        assert r.status == CommandStatus.SUCCESS
        assert r.details["broken_count"] == 1
        assert isinstance(r.details["broken"], list)

    def test_handles_empty_output(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output="",
            ),
        )
        r = svc.scan_broken_shortcuts()
        assert r.status == CommandStatus.SUCCESS
        assert r.details["broken_count"] == 0

    def test_parse_error_returns_error(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output="not json {",
            ),
        )
        r = svc.scan_broken_shortcuts()
        assert r.status == CommandStatus.ERROR

    def test_propagates_powershell_error(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.ERROR,
                output="",
                error="PS failed",
            ),
        )
        r = svc.scan_broken_shortcuts()
        assert r.status == CommandStatus.ERROR


# ============================================================
# delete_broken_shortcuts — input validation
# ============================================================


class TestDeleteBrokenShortcutsInputs:
    def test_rejects_non_list(self):
        r = svc.delete_broken_shortcuts(None)
        assert r.status == CommandStatus.ERROR

    def test_rejects_empty_list(self):
        r = svc.delete_broken_shortcuts([])
        assert r.status == CommandStatus.ERROR

    def test_rejects_oversize_batch(self):
        big = ["a.lnk"] * 501
        r = svc.delete_broken_shortcuts(big)
        assert r.status == CommandStatus.ERROR
        assert "max 500" in r.output

    def test_rejects_when_no_valid_lnk(self):
        r = svc.delete_broken_shortcuts([r"C:\not_a_lnk.txt", 42, None])
        assert r.status == CommandStatus.ERROR


# ============================================================
# delete_broken_shortcuts — happy path with mocked PowerShell
# ============================================================


class TestDeleteBrokenShortcutsExecution:
    def test_counts_deleted(self, monkeypatch):
        payload = {
            "results": [
                {"path": r"C:\Users\u\Desktop\a.lnk", "status": "deleted"},
                {"path": r"C:\Users\u\Desktop\b.lnk", "status": "deleted"},
                {
                    "path": r"C:\Users\u\Desktop\c.lnk",
                    "status": "skipped_target_exists",
                },
            ],
            "count": 3,
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(payload),
            ),
        )
        r = svc.delete_broken_shortcuts(
            [
                r"C:\Users\u\Desktop\a.lnk",
                r"C:\Users\u\Desktop\b.lnk",
                r"C:\Users\u\Desktop\c.lnk",
            ]
        )
        assert r.status == CommandStatus.SUCCESS
        assert r.details["deleted_count"] == 2
        assert r.details["input_count"] == 3
