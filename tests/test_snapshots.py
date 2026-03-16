"""Tests for action-aware snapshot system."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.snapshots import (
    capture_action_snapshot, _base_snapshot, _safe_dir_size_mb,
    snapshot_cleanup, snapshot_network, snapshot_power,
    snapshot_update, snapshot_security, snapshot_storage,
    snapshot_repair, snapshot_explorer,
)


class TestBaseSnapshot:
    """Test base snapshot functionality."""

    def test_base_snapshot_has_timestamp(self):
        snap = _base_snapshot()
        assert 'captured_at' in snap
        assert snap['captured_at']  # not empty

    def test_base_snapshot_has_ram_fields(self):
        snap = _base_snapshot()
        # psutil is available in test env
        assert 'ram_used_gb' in snap
        assert 'ram_percent' in snap
        assert isinstance(snap['ram_percent'], float)

    def test_base_snapshot_has_cpu(self):
        snap = _base_snapshot()
        assert 'cpu_percent' in snap

    def test_base_snapshot_has_disk(self):
        snap = _base_snapshot()
        assert 'disk_free_gb' in snap


class TestSafeDirSize:
    """Test directory size helper."""

    def test_nonexistent_dir_returns_negative(self):
        result = _safe_dir_size_mb('/nonexistent/path/xyz')
        assert result == -1.0

    def test_existing_dir_returns_number(self, tmp_path):
        # Create a small file
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _safe_dir_size_mb(str(tmp_path))
        assert result >= 0.0


class TestCleanupSnapshot:
    """Test cleanup-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_cleanup('cleanup.user_temp')
        assert snap['category'] == 'cleanup'

    def test_has_temp_fields(self):
        snap = snapshot_cleanup('cleanup.user_temp')
        assert 'user_temp_mb' in snap
        assert 'windows_temp_mb' in snap
        assert 'prefetch_mb' in snap
        assert 'sw_distribution_mb' in snap

    def test_has_timestamp(self):
        snap = snapshot_cleanup('cleanup.user_temp')
        assert 'captured_at' in snap


class TestNetworkSnapshot:
    """Test network-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_network('network.flush_dns')
        assert snap['category'] == 'network'

    def test_non_windows_marks_not_applicable(self):
        if sys.platform != 'win32':
            snap = snapshot_network('network.flush_dns')
            assert snap['adapters'] == 'not_applicable'


class TestPowerSnapshot:
    """Test power-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_power('power.set_balanced')
        assert snap['category'] == 'power'

    def test_has_active_plan(self):
        snap = snapshot_power('power.set_balanced')
        assert 'active_plan' in snap


class TestUpdateSnapshot:
    """Test update-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_update('update.hard_reset')
        assert snap['category'] == 'update'

    def test_has_wu_fields(self):
        snap = snapshot_update('update.hard_reset')
        assert 'wu_services' in snap
        if sys.platform == 'win32':
            assert 'software_distribution_exists' in snap
            assert 'catroot2_exists' in snap
            assert 'reboot_pending' in snap


class TestSecuritySnapshot:
    """Test security-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_security('security.quick_scan')
        assert snap['category'] == 'security'

    def test_has_defender_field(self):
        snap = snapshot_security('security.quick_scan')
        assert 'defender' in snap


class TestStorageSnapshot:
    """Test storage-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_storage('cleanup.retrim')
        assert snap['category'] == 'storage'

    def test_has_disks_field(self):
        snap = snapshot_storage('cleanup.retrim')
        assert 'disks' in snap


class TestRepairSnapshot:
    """Test repair-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_repair('repair.sfc')
        assert snap['category'] == 'repair'


class TestExplorerSnapshot:
    """Test explorer-specific snapshots."""

    def test_has_category(self):
        snap = snapshot_explorer('cleanup.restart_explorer')
        assert snap['category'] == 'explorer'

    def test_has_explorer_running(self):
        snap = snapshot_explorer('cleanup.restart_explorer')
        assert 'explorer_running' in snap


class TestDispatcher:
    """Test action-to-collector dispatch."""

    def test_cleanup_dispatches_correctly(self):
        snap = capture_action_snapshot('cleanup.user_temp', 'before')
        assert snap['category'] == 'cleanup'
        assert snap['phase'] == 'before'
        assert snap['action_id'] == 'cleanup.user_temp'

    def test_network_dispatches_correctly(self):
        snap = capture_action_snapshot('network.flush_dns', 'after')
        assert snap['category'] == 'network'
        assert snap['phase'] == 'after'

    def test_power_dispatches_correctly(self):
        snap = capture_action_snapshot('power.set_balanced', 'before')
        assert snap['category'] == 'power'

    def test_update_dispatches_correctly(self):
        snap = capture_action_snapshot('update.scan', 'before')
        assert snap['category'] == 'update'

    def test_security_dispatches_correctly(self):
        snap = capture_action_snapshot('security.quick_scan', 'before')
        assert snap['category'] == 'security'

    def test_repair_dispatches_correctly(self):
        snap = capture_action_snapshot('repair.sfc', 'before')
        assert snap['category'] == 'repair'

    def test_explorer_override(self):
        """cleanup.restart_explorer should use explorer collector."""
        snap = capture_action_snapshot('cleanup.restart_explorer', 'before')
        assert snap['category'] == 'explorer'

    def test_retrim_override(self):
        """cleanup.retrim should use storage collector."""
        snap = capture_action_snapshot('cleanup.retrim', 'before')
        assert snap['category'] == 'storage'

    def test_unknown_action_falls_back(self):
        snap = capture_action_snapshot('unknown.action', 'before')
        assert snap['category'] == 'generic'
        assert snap['phase'] == 'before'
