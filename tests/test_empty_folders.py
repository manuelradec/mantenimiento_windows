"""Tests for services.empty_folders (M2, Phase A).

Covers:
- _is_protected filters obvious system paths.
- scan_empty_folders refuses protected roots, parses output correctly.
- delete_empty_folders rejects non-list, oversize, and protected inputs.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import empty_folders as svc
from services.command_runner import CommandResult, CommandStatus


class TestProtectedFilter:
    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Windows\System32",
            r"C:\Program Files\App",
            r"C:\Users\u\AppData\Local\Temp",
            r"C:\$Recycle.Bin\S-1-5",
            r"C:\Users\u\OneDrive\foo",
            r"D:\repo\.git",
            r"D:\proj\node_modules",
            r"",
        ],
    )
    def test_protected(self, path):
        assert svc._is_protected(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Users\u\Desktop\Photos\old",
            r"D:\backup\2026",
            r"C:\Users\u\Documents\projects\demo",
        ],
    )
    def test_not_protected(self, path):
        assert svc._is_protected(path) is False


class TestScanEmptyFolders:
    def test_rejects_protected_root(self):
        r = svc.scan_empty_folders(r"C:\Windows\System32")
        assert r.status == CommandStatus.ERROR
        assert "protected" in r.output.lower()

    def test_parses_normal_payload(self, monkeypatch):
        payload = {
            "root": r"C:\Users\u",
            "count": 2,
            "items": [
                {
                    "path": r"C:\Users\u\Documents\old1",
                    "name": "old1",
                    "parent": r"C:\Users\u\Documents",
                },
                {
                    "path": r"C:\Users\u\Pictures\old2",
                    "name": "old2",
                    "parent": r"C:\Users\u\Pictures",
                },
            ],
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(payload),
            ),
        )
        r = svc.scan_empty_folders(r"C:\Users\u\Documents")
        assert r.status == CommandStatus.SUCCESS
        assert r.details["count"] == 2
        assert len(r.details["items"]) == 2

    def test_filters_protected_items_server_side(self, monkeypatch):
        # Server returns one legit + one inside AppData → AppData should be dropped.
        payload = {
            "root": r"C:\Users\u",
            "count": 2,
            "items": [
                {"path": r"C:\Users\u\Documents\ok", "name": "ok"},
                {"path": r"C:\Users\u\AppData\Local\garbage", "name": "garbage"},
            ],
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(payload),
            ),
        )
        r = svc.scan_empty_folders(r"C:\Users\u")
        assert r.status == CommandStatus.SUCCESS
        assert r.details["count"] == 1


class TestDeleteEmptyFoldersInputs:
    def test_rejects_non_list(self):
        r = svc.delete_empty_folders(None)
        assert r.status == CommandStatus.ERROR

    def test_rejects_empty(self):
        r = svc.delete_empty_folders([])
        assert r.status == CommandStatus.ERROR

    def test_rejects_oversize(self):
        big = [r"C:\Users\u\x"] * 501
        r = svc.delete_empty_folders(big)
        assert r.status == CommandStatus.ERROR
        assert "max 500" in r.output

    def test_filters_all_protected_paths(self):
        r = svc.delete_empty_folders(
            [r"C:\Windows\System32\x", r"C:\Users\u\AppData\y"]
        )
        assert r.status == CommandStatus.ERROR

    def test_counts_deleted(self, monkeypatch):
        payload = {
            "results": [
                {"path": r"C:\Users\u\Documents\a", "status": "deleted"},
                {"path": r"C:\Users\u\Documents\b", "status": "skipped_not_empty"},
            ],
            "count": 2,
        }
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.SUCCESS,
                output=json.dumps(payload),
            ),
        )
        r = svc.delete_empty_folders(
            [r"C:\Users\u\Documents\a", r"C:\Users\u\Documents\b"]
        )
        assert r.status == CommandStatus.SUCCESS
        assert r.details["deleted_count"] == 1
        assert r.details["input_count"] == 2
