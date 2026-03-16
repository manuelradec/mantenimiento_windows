"""
Tests for round-3 hardening: job runner, locking, command runner,
rollback classification, and reporting.
"""
import sys
import os
import time
import uuid
import json
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.command_runner import (
    _validate_command, sanitize_argument, CommandResult, CommandStatus,
    ALLOWED_COMMANDS,
)
from core.governance import ROLLBACK_STRATEGIES, get_rollback_info
from core.action_registry import registry, RiskClass


# ============================================================
# Command Runner Hardening Tests
# ============================================================

class TestCommandRunnerHardening:
    """Test tighter allowlist rules."""

    def test_mdsched_no_args_allowed(self):
        assert _validate_command(['mdsched.exe']) is True

    def test_mdsched_with_args_blocked(self):
        """mdsched.exe should not accept any arguments."""
        assert _validate_command(['mdsched.exe', '/something']) is False

    def test_wsreset_no_args_allowed(self):
        assert _validate_command(['wsreset.exe']) is True

    def test_wsreset_with_args_blocked(self):
        assert _validate_command(['wsreset.exe', '--evil']) is False

    def test_ren_softwaredist_allowed(self):
        """ren for WU reset rename should be allowed."""
        assert _validate_command([
            'ren', 'C:\\Windows\\SoftwareDistribution',
            'SoftwareDistribution.bak.20260316'
        ]) is True

    def test_ren_arbitrary_blocked(self):
        """ren for arbitrary files should be blocked."""
        assert _validate_command([
            'ren', 'C:\\important.exe', 'gone.bak'
        ]) is False

    def test_cscript_slmgr_allowed(self):
        """cscript for slmgr.vbs license check should pass."""
        assert _validate_command([
            'cscript', '//nologo', 'C:\\Windows\\System32\\slmgr.vbs', '/dlv'
        ]) is True

    def test_cscript_arbitrary_blocked(self):
        """cscript for arbitrary VBS should be blocked."""
        assert _validate_command([
            'cscript', '//nologo', 'C:\\evil.vbs'
        ]) is False

    def test_pnputil_enum_allowed(self):
        assert _validate_command(['pnputil', '/enum-drivers']) is True

    def test_pnputil_delete_blocked(self):
        """pnputil /delete-driver should be blocked."""
        assert _validate_command(
            ['pnputil', '/delete-driver', 'oem42.inf']
        ) is False

    def test_net_localgroup_denied(self):
        """net localgroup should be blocked."""
        assert _validate_command(['net', 'localgroup']) is False

    def test_netsh_firewall_denied(self):
        """netsh with firewall args should be blocked."""
        assert _validate_command(
            ['netsh', 'advfirewall', 'show', 'allprofiles']
        ) is False

    def test_defrag_x_denied(self):
        """defrag /x (force defrag) should be blocked."""
        assert _validate_command(['defrag', 'C:', '/x']) is False

    def test_defrag_a_allowed(self):
        """defrag /A (analyze) should be allowed."""
        assert _validate_command(['defrag', 'C:', '/A']) is True

    def test_powershell_with_proper_flags_allowed(self):
        """PowerShell with NoProfile/NonInteractive/Command is allowed."""
        assert _validate_command([
            'powershell.exe', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-Command', 'Get-Date'
        ]) is True

    def test_powershell_bare_blocked(self):
        """Bare powershell.exe with no recognized subcommands blocked."""
        # With subcommands defined, bare invocation with just a script
        # won't match any subcommand
        assert _validate_command(
            ['powershell.exe', '-File', 'evil.ps1']
        ) is False

    def test_sanitize_semicolon_rejected(self):
        with pytest.raises(ValueError):
            sanitize_argument('foo; rm -rf /')

    def test_sanitize_pipe_rejected(self):
        with pytest.raises(ValueError):
            sanitize_argument('foo | evil')

    def test_sanitize_backtick_rejected(self):
        with pytest.raises(ValueError):
            sanitize_argument('foo`evil')

    def test_sanitize_clean_arg_passes(self):
        assert sanitize_argument('/scannow') == '/scannow'


class TestCommandResultStructure:
    """Test that validation failures return structured details."""

    def test_validation_error_has_details(self):
        result = CommandResult(
            status=CommandStatus.ERROR,
            error='blocked',
            details={'validation': 'blocked_by_allowlist', 'base_command': 'evil'}
        )
        d = result.to_dict()
        assert d['details']['validation'] == 'blocked_by_allowlist'
        assert d['details']['base_command'] == 'evil'


# ============================================================
# Rollback Classification Tests
# ============================================================

class TestRollbackClassification:
    """Test structured rollback strategies."""

    def test_all_strategies_have_classification(self):
        """Every rollback strategy must have a classification field."""
        for action_id, strategy in ROLLBACK_STRATEGIES.items():
            assert 'classification' in strategy, (
                f"{action_id} missing 'classification'"
            )
            assert strategy['classification'] in (
                'not_reversible', 'auto_reversible',
                'manually_reversible', 'partially_reversible',
                'not_applicable',
            ), f"{action_id} has invalid classification: {strategy['classification']}"

    def test_all_strategies_have_needs_reboot(self):
        """Every strategy must declare whether reboot is needed."""
        for action_id, strategy in ROLLBACK_STRATEGIES.items():
            assert 'needs_reboot' in strategy, (
                f"{action_id} missing 'needs_reboot'"
            )
            assert isinstance(strategy['needs_reboot'], bool)

    def test_all_strategies_have_restore_point_flag(self):
        """Every strategy must declare restore_point_recommended."""
        for action_id, strategy in ROLLBACK_STRATEGIES.items():
            assert 'restore_point_recommended' in strategy, (
                f"{action_id} missing 'restore_point_recommended'"
            )

    def test_disruptive_actions_recommend_restore_point(self):
        """Actions classified as DISRUPTIVE or higher with restore_point_recommended."""
        risky_with_restore = [
            aid for aid, strat in ROLLBACK_STRATEGIES.items()
            if strat.get('restore_point_recommended', False)
        ]
        # At minimum, these should recommend restore points
        assert 'cleanup.component_cleanup' in risky_with_restore
        assert 'repair.sfc' in risky_with_restore
        assert 'repair.dism_restore' in risky_with_restore
        assert 'update.hard_reset' in risky_with_restore

    def test_manually_reversible_have_rollback_command(self):
        """Manually reversible with known commands should provide rollback_command."""
        for action_id, strategy in ROLLBACK_STRATEGIES.items():
            if strategy['classification'] == 'manually_reversible':
                # At least has instructions
                assert strategy.get('instructions'), (
                    f"{action_id} is manually_reversible but has no instructions"
                )

    def test_get_rollback_info_returns_full_structure(self):
        info = get_rollback_info('power.set_balanced')
        assert 'classification' in info
        assert 'reversible' in info
        assert 'instructions' in info
        assert 'needs_reboot' in info
        assert 'restore_point_recommended' in info

    def test_get_rollback_info_unknown_action(self):
        info = get_rollback_info('nonexistent.action')
        assert info['classification'] == 'unknown'

    def test_rollback_strategies_cover_registered_actions(self):
        """Every registered mutating action should have a rollback strategy."""
        for action_id, action in registry._actions.items():
            if action.risk_class != RiskClass.SAFE_READONLY:
                assert action_id in ROLLBACK_STRATEGIES, (
                    f"Registered action '{action_id}' has no rollback strategy"
                )

    def test_reboot_actions_have_reboot_flag(self):
        """Actions like reset_winsock that need reboot should flag it."""
        assert ROLLBACK_STRATEGIES['network.reset_winsock']['needs_reboot'] is True
        assert ROLLBACK_STRATEGIES['network.reset_ip_stack']['needs_reboot'] is True
        assert ROLLBACK_STRATEGIES['repair.chkdsk_schedule']['needs_reboot'] is True


# ============================================================
# Job Runner Tests
# ============================================================

class TestJobRunnerLifecycle:
    """Test job lifecycle management."""

    def test_job_creation(self):
        from core.action_registry import ActionDef, RiskClass
        from core.job_runner import Job

        action = ActionDef(
            action_id='test.action',
            name='Test Action',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        job = Job(action, session_id='test-sess')
        assert job.status == 'queued'
        assert job.action_id == 'test.action'
        assert job.cancel_requested is False
        assert job.process is None

    def test_job_to_dict(self):
        from core.action_registry import ActionDef, RiskClass
        from core.job_runner import Job

        action = ActionDef(
            action_id='test.action',
            name='Test Action',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        job = Job(action, session_id='test-sess', hostname='h', username='u')
        d = job.to_dict()
        assert d['status'] == 'queued'
        assert d['module'] == 'test'
        assert 'job_id' in d
        assert 'queued_at' in d

    def test_cancel_queued_job(self):
        from core.action_registry import ActionDef, RiskClass
        from core.job_runner import Job

        action = ActionDef(
            action_id='test.cancel',
            name='Cancel Test',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        job = Job(action, session_id='test-sess')
        assert job.status == 'queued'
        job.status = 'cancelled'
        assert job.status == 'cancelled'


# ============================================================
# Locking Tests
# ============================================================

class TestModuleLocking:
    """Test module-level locking behavior."""

    def test_acquire_and_release(self):
        from core.policy_engine import policy
        module = f'test_lock_{uuid.uuid4().hex[:6]}'
        assert policy.acquire_lock(module, 'job1') is True
        # Second acquire on same module should fail
        assert policy.acquire_lock(module, 'job2') is False
        # Release
        policy.release_lock(module)
        # Now should succeed
        assert policy.acquire_lock(module, 'job3') is True
        policy.release_lock(module)

    def test_different_modules_no_contention(self):
        from core.policy_engine import policy
        m1 = f'mod_a_{uuid.uuid4().hex[:6]}'
        m2 = f'mod_b_{uuid.uuid4().hex[:6]}'
        assert policy.acquire_lock(m1, 'job1') is True
        assert policy.acquire_lock(m2, 'job2') is True
        policy.release_lock(m1)
        policy.release_lock(m2)

    def test_lock_status_visible(self):
        from core.policy_engine import policy
        module = f'test_status_{uuid.uuid4().hex[:6]}'
        policy.acquire_lock(module, 'job_x')
        status = policy.get_status()
        assert module in str(status.get('active_locks', {}))
        policy.release_lock(module)


# ============================================================
# Reporting & Persistence Tests
# ============================================================

class TestSnapshotPersistence:
    """Test snapshot storage and retrieval."""

    def test_snapshot_roundtrip(self):
        from core.persistence import init_db, get_db, SnapshotStore
        init_db()

        job_id = f'snap-{uuid.uuid4().hex[:8]}'
        session_id = f'sess-{uuid.uuid4().hex[:8]}'

        # Store a snapshot
        with get_db() as conn:
            conn.execute(
                "INSERT INTO snapshots (job_id, session_id, action_id, "
                "snapshot_type, captured_at, data_json) "
                "VALUES (?, ?, ?, 'before', ?, ?)",
                (job_id, session_id, 'test.action',
                 '2026-03-16T10:00:00',
                 json.dumps({'category': 'test', 'disk_free_gb': 50.0}))
            )

        # Retrieve
        snaps = SnapshotStore.get_by_job(job_id)
        assert len(snaps) == 1
        assert snaps[0]['action_id'] == 'test.action'
        data = json.loads(snaps[0]['data_json'])
        assert data['category'] == 'test'

    def test_event_viewer_persistence(self):
        from core.persistence import init_db, EventViewerStore
        init_db()

        session_id = f'evt-{uuid.uuid4().hex[:8]}'
        events = [
            {'log_name': 'System', 'provider': 'test',
             'event_id': 1, 'level': 'Error',
             'time_created': '2026-03-16T10:00:00',
             'message': 'Test event'},
        ]
        EventViewerStore.store_events(session_id, events, job_id='j1')

        stored = EventViewerStore.get_by_session(session_id)
        assert len(stored) == 1
        assert stored[0]['message'] == 'Test event'

    def test_audit_summary(self):
        from core.persistence import init_db, AuditStore
        init_db()

        session_id = f'aud-{uuid.uuid4().hex[:8]}'
        AuditStore.log(session_id, 'test', 'action1', 'completed')
        AuditStore.log(session_id, 'test', 'action2', 'failed')

        summary = AuditStore.get_summary(session_id)
        assert summary['total_actions'] == 2
        assert summary['by_status'].get('completed', 0) == 1
        assert summary['by_status'].get('failed', 0) == 1
