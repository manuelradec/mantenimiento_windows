"""Tests for the governance layer, command runner, and job runner."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.action_registry import registry, ActionDef, RiskClass, OperationMode
from core.policy_engine import PolicyEngine
from core.persistence import init_db
from services.command_runner import (
    CommandResult, CommandStatus, sanitize_argument,
    _validate_command, ALLOWED_COMMANDS
)


class TestCommandValidation:
    """Test fine-grained command allowlist enforcement."""

    def test_sfc_scannow_allowed(self):
        assert _validate_command(['sfc', '/scannow']) is True

    def test_sfc_unknown_arg_blocked(self):
        # sfc with no known subcommand in args but args present
        assert _validate_command(['sfc', '/delete']) is False

    def test_dism_checkhealth_allowed(self):
        assert _validate_command(['DISM', '/Online', '/Cleanup-Image', '/CheckHealth']) is True

    def test_dism_random_args_blocked(self):
        assert _validate_command(['DISM', '/Delete-Image']) is False

    def test_netsh_winsock_reset_allowed(self):
        assert _validate_command(['netsh', 'winsock', 'reset']) is True

    def test_netsh_firewall_not_in_subcommands(self):
        # 'firewall' is not in allowed subcommands for netsh
        assert _validate_command(['netsh', 'firewall', 'set']) is False

    def test_net_stop_allowed(self):
        assert _validate_command(['net', 'stop', 'wuauserv']) is True

    def test_net_user_denied(self):
        """net user is denied as first argument."""
        assert _validate_command(['net', 'user', 'admin']) is False

    def test_net_group_denied(self):
        """net group is denied as first argument."""
        assert _validate_command(['net', 'group']) is False

    def test_sc_delete_denied(self):
        """sc delete is explicitly denied."""
        assert _validate_command(['sc', 'delete', 'MyService']) is False

    def test_sc_config_allowed(self):
        assert _validate_command(['sc', 'config', 'w32time', 'start=auto']) is True

    def test_unknown_command_blocked(self):
        assert _validate_command(['evil.exe', '/payload']) is False

    def test_empty_command_blocked(self):
        assert _validate_command([]) is False

    def test_powershell_allowed(self):
        assert _validate_command(['powershell.exe', '-Command', 'Get-Process']) is True

    def test_ipconfig_flushdns_allowed(self):
        assert _validate_command(['ipconfig', '/flushdns']) is True

    def test_ipconfig_no_args_allowed(self):
        """ipconfig with no args should be allowed (subcommands check only applies if args present)."""
        assert _validate_command(['ipconfig']) is True

    def test_pnputil_enum_drivers_allowed(self):
        assert _validate_command(['pnputil', '/enum-drivers']) is True


class TestSanitizeArgument:
    """Test argument sanitization."""

    def test_safe_argument(self):
        assert sanitize_argument('C:\\Windows\\Temp') == 'C:\\Windows\\Temp'

    def test_semicolon_blocked(self):
        with pytest.raises(ValueError):
            sanitize_argument('arg; rm -rf /')

    def test_pipe_blocked(self):
        with pytest.raises(ValueError):
            sanitize_argument('arg | evil')

    def test_backtick_blocked(self):
        with pytest.raises(ValueError):
            sanitize_argument('arg`evil')

    def test_path_traversal_blocked(self):
        with pytest.raises(ValueError):
            sanitize_argument('../../etc/passwd')

    def test_newline_blocked(self):
        with pytest.raises(ValueError):
            sanitize_argument('arg\nmalicious')


class TestCommandResult:
    """Test CommandResult structure."""

    def test_to_dict_completeness(self):
        result = CommandResult(
            status=CommandStatus.SUCCESS,
            output='test output',
            error='',
            return_code=0,
            command='test cmd',
            duration=1.5,
        )
        d = result.to_dict()
        assert d['status'] == 'success'
        assert d['output'] == 'test output'
        assert d['duration'] == 1.5
        assert d['return_code'] == 0
        assert 'operation_id' in d
        assert 'timestamp' in d

    def test_status_properties(self):
        success = CommandResult(status=CommandStatus.SUCCESS)
        assert success.is_success and not success.is_error

        error = CommandResult(status=CommandStatus.ERROR)
        assert error.is_error and not error.is_success

        timeout = CommandResult(status=CommandStatus.TIMEOUT)
        assert timeout.is_error


class TestGovernanceRollback:
    """Test rollback strategy metadata."""

    def test_rollback_strategies_cover_registered_actions(self):
        from core.governance import ROLLBACK_STRATEGIES
        # All SAFE_MUTATION and above actions should have rollback info
        for action in registry.list_all():
            if action.risk_class != RiskClass.SAFE_READONLY:
                info = ROLLBACK_STRATEGIES.get(action.action_id)
                assert info is not None, (
                    f"Missing rollback strategy for {action.action_id}"
                )

    def test_rollback_info_structure(self):
        from core.governance import get_rollback_info
        info = get_rollback_info('cleanup.user_temp')
        assert 'reversible' in info
        assert 'instructions' in info
        assert info['reversible'] in ('no', 'auto', 'manual', 'partial', 'n/a', 'unknown')


class TestActionRegistry:
    """Test action registry completeness."""

    def test_all_risk_classes_have_actions(self):
        for risk in RiskClass:
            actions = registry.list_by_risk(risk)
            assert len(actions) > 0, f"No actions for {risk.value}"

    def test_destructive_actions_require_admin_and_confirmation(self):
        for action in registry.list_by_risk(RiskClass.DESTRUCTIVE):
            assert action.requires_admin, f"{action.action_id} missing requires_admin"
            assert action.requires_confirmation, f"{action.action_id} missing requires_confirmation"

    def test_action_ids_are_unique(self):
        all_actions = registry.list_all()
        ids = [a.action_id for a in all_actions]
        assert len(ids) == len(set(ids)), "Duplicate action IDs found"

    def test_safe_mutation_count(self):
        safe_mut = registry.list_by_risk(RiskClass.SAFE_MUTATION)
        assert len(safe_mut) >= 10

    def test_mode_filtering(self):
        diagnostic_only = registry.list_allowed(OperationMode.DIAGNOSTIC)
        for a in diagnostic_only:
            assert a.risk_class == RiskClass.SAFE_READONLY

        expert = registry.list_allowed(OperationMode.EXPERT)
        risk_classes = set(a.risk_class for a in expert)
        assert RiskClass.DESTRUCTIVE in risk_classes


class TestPolicyEngineExtended:
    """Extended policy engine tests."""

    def setup_method(self):
        self.policy = PolicyEngine()

    def test_safe_maintenance_blocks_disruptive(self):
        action = ActionDef(
            action_id='test.disruptive', name='Test', module='test',
            risk_class=RiskClass.DISRUPTIVE, requires_admin=True,
        )
        result = self.policy.validate_action(action, is_admin=True)
        assert not result['allowed']
        assert result['violation_type'] == 'mode_restriction'

    def test_advanced_allows_disruptive(self):
        action = ActionDef(
            action_id='test.disruptive', name='Test', module='test',
            risk_class=RiskClass.DISRUPTIVE, requires_admin=True,
        )
        self.policy.set_mode(OperationMode.ADVANCED)
        result = self.policy.validate_action(action, is_admin=True)
        assert result['allowed']

    def test_advanced_blocks_destructive(self):
        action = ActionDef(
            action_id='test.destructive', name='Test', module='test',
            risk_class=RiskClass.DESTRUCTIVE, requires_admin=True,
        )
        self.policy.set_mode(OperationMode.ADVANCED)
        result = self.policy.validate_action(action, is_admin=True)
        assert not result['allowed']

    def test_reboot_warning_in_result(self):
        action = ActionDef(
            action_id='test.reboot', name='Test', module='test',
            risk_class=RiskClass.SAFE_MUTATION, needs_reboot=True,
        )
        result = self.policy.validate_action(action, is_admin=False)
        assert any('reboot' in w.lower() for w in result.get('warnings', []))

    def test_restore_point_warning(self):
        action = ActionDef(
            action_id='test.rp', name='Test', module='test',
            risk_class=RiskClass.SAFE_MUTATION, needs_restore_point=True,
        )
        result = self.policy.validate_action(action, is_admin=False)
        assert any('restore' in w.lower() for w in result.get('warnings', []))

    def test_concurrent_module_locks(self):
        """Different modules can be locked simultaneously."""
        assert self.policy.acquire_lock('repair', 'job-1')
        assert self.policy.acquire_lock('network', 'job-2')
        assert not self.policy.acquire_lock('repair', 'job-3')
        self.policy.release_lock('repair')
        self.policy.release_lock('network')

    def test_policy_status_includes_locks(self):
        self.policy.acquire_lock('cleanup', 'job-x')
        status = self.policy.get_status()
        assert 'cleanup' in status['active_locks']
        self.policy.release_lock('cleanup')


class TestPersistenceExtended:
    """Extended persistence tests."""

    def test_snapshot_persistence(self):
        from core.persistence import init_db, SnapshotStore, get_db
        init_db()
        import json
        with get_db() as conn:
            conn.execute(
                "INSERT INTO snapshots (job_id, session_id, action_id, snapshot_type, "
                "captured_at, data_json) VALUES (?, ?, ?, ?, ?, ?)",
                ('job-1', 'sess-1', 'test.action', 'before', '2025-01-01T00:00:00',
                 json.dumps({'disk_free_gb': 50}))
            )
        snaps = SnapshotStore.get_by_job('job-1')
        assert len(snaps) >= 1
        assert snaps[0]['snapshot_type'] == 'before'

    def test_job_lifecycle(self):
        import uuid
        from core.persistence import init_db, JobStore, SessionStore
        init_db()
        jid = f'test-job-{uuid.uuid4().hex[:8]}'
        sid = f'test-sess-{uuid.uuid4().hex[:8]}'
        SessionStore.create(sid, 'h', 'u')
        JobStore.create(
            job_id=jid, session_id=sid,
            action_id='test.action', action_name='Test',
            module='test', risk_class='safe_mutation',
        )
        job = JobStore.get(jid)
        assert job is not None
        assert job['status'] == 'queued'

        JobStore.update_started(jid)
        job = JobStore.get(jid)
        assert job['status'] == 'running'

        JobStore.update_completed(jid, 'completed', stdout='done', duration_ms=100)
        job = JobStore.get(jid)
        assert job['status'] == 'completed'
        assert job['duration_ms'] == 100

    def test_job_cancellation(self):
        import uuid
        from core.persistence import init_db, JobStore, SessionStore
        init_db()
        jid = f'cancel-{uuid.uuid4().hex[:8]}'
        sid = f'cancel-sess-{uuid.uuid4().hex[:8]}'
        SessionStore.create(sid, 'h', 'u')
        JobStore.create(
            job_id=jid, session_id=sid,
            action_id='test.action', action_name='Test',
            module='test', risk_class='safe_mutation',
        )
        JobStore.cancel(jid)
        job = JobStore.get(jid)
        assert job['status'] == 'cancelled'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
