"""Tests for the policy engine."""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.action_registry import (
    ActionDef, RiskClass, OperationMode, registry
)
from core.policy_engine import PolicyEngine


class TestPolicyEngine:
    """Test suite for PolicyEngine."""

    def setup_method(self):
        self.policy = PolicyEngine()

    def test_default_mode_is_safe_maintenance(self):
        assert self.policy.mode == OperationMode.SAFE_MAINTENANCE

    def test_set_mode(self):
        self.policy.set_mode(OperationMode.DIAGNOSTIC)
        assert self.policy.mode == OperationMode.DIAGNOSTIC

    def test_diagnostic_mode_blocks_mutations(self):
        action = ActionDef(
            action_id='test.mutation',
            name='Test Mutation',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        self.policy.set_mode(OperationMode.DIAGNOSTIC)
        result = self.policy.validate_action(action, is_admin=True)
        assert not result['allowed']
        assert result['violation_type'] == 'mode_restriction'

    def test_diagnostic_mode_allows_readonly(self):
        action = ActionDef(
            action_id='test.readonly',
            name='Test ReadOnly',
            module='test',
            risk_class=RiskClass.SAFE_READONLY,
        )
        self.policy.set_mode(OperationMode.DIAGNOSTIC)
        result = self.policy.validate_action(action, is_admin=False)
        assert result['allowed']

    def test_safe_maintenance_allows_safe_mutations(self):
        action = ActionDef(
            action_id='test.safe',
            name='Test Safe',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        result = self.policy.validate_action(action, is_admin=False)
        assert result['allowed']

    def test_safe_maintenance_blocks_destructive(self):
        action = ActionDef(
            action_id='test.destructive',
            name='Test Destructive',
            module='test',
            risk_class=RiskClass.DESTRUCTIVE,
            requires_admin=True,
        )
        result = self.policy.validate_action(action, is_admin=True)
        assert not result['allowed']

    def test_admin_required_blocks_non_admin(self):
        action = ActionDef(
            action_id='test.admin',
            name='Test Admin',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
            requires_admin=True,
        )
        result = self.policy.validate_action(action, is_admin=False)
        assert not result['allowed']
        assert result['violation_type'] == 'requires_admin'

    def test_expert_mode_allows_destructive(self):
        action = ActionDef(
            action_id='test.destructive',
            name='Test Destructive',
            module='test',
            risk_class=RiskClass.DESTRUCTIVE,
            requires_admin=True,
        )
        self.policy.set_mode(OperationMode.EXPERT)
        result = self.policy.validate_action(action, is_admin=True)
        assert result['allowed']

    def test_module_locking(self):
        assert self.policy.acquire_lock('test_module', 'job-1')
        assert not self.policy.acquire_lock('test_module', 'job-2')
        self.policy.release_lock('test_module')
        assert self.policy.acquire_lock('test_module', 'job-3')
        self.policy.release_lock('test_module')

    def test_confirmation_required(self):
        action = ActionDef(
            action_id='test.confirm',
            name='Test Confirm',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
            requires_confirmation=True,
            confirm_message='Are you sure?',
        )
        result = self.policy.validate_action(action, is_admin=False)
        assert result['allowed']
        assert result['needs_confirmation']

    def test_confirmation_token(self):
        action = ActionDef(
            action_id='test.confirm',
            name='Test Confirm',
            module='test',
            risk_class=RiskClass.SAFE_MUTATION,
            requires_confirmation=True,
        )
        token = 'test-token-123'
        self.policy.add_confirmation(token)
        result = self.policy.validate_action(action, is_admin=False,
                                             confirmation_token=token)
        assert result['allowed']
        assert not result['needs_confirmation']

    def test_locked_module_rejects(self):
        action = ActionDef(
            action_id='test.lock',
            name='Test Lock',
            module='repair',
            risk_class=RiskClass.SAFE_MUTATION,
        )
        self.policy.acquire_lock('repair', 'existing-job')
        result = self.policy.validate_action(action, is_admin=False)
        assert not result['allowed']
        assert result['violation_type'] == 'locked'
        self.policy.release_lock('repair')


class TestActionRegistry:
    """Test suite for ActionRegistry."""

    def test_registry_populated(self):
        """Registry should be auto-populated on import."""
        all_actions = registry.list_all()
        assert len(all_actions) > 30, f"Expected 30+ actions, got {len(all_actions)}"

    def test_all_risk_classes_represented(self):
        """Every risk class should have at least one action."""
        for risk in RiskClass:
            actions = registry.list_by_risk(risk)
            assert len(actions) > 0, f"No actions for risk class: {risk.value}"

    def test_diagnostic_actions_exist(self):
        action = registry.get('diag.system_overview')
        assert action is not None
        assert action.risk_class == RiskClass.SAFE_READONLY

    def test_destructive_actions_require_admin(self):
        destructive = registry.list_by_risk(RiskClass.DESTRUCTIVE)
        for action in destructive:
            assert action.requires_admin, f"{action.action_id} should require admin"
            assert action.requires_confirmation, f"{action.action_id} should require confirmation"

    def test_list_allowed_diagnostic_mode(self):
        allowed = registry.list_allowed(OperationMode.DIAGNOSTIC)
        for a in allowed:
            assert a.risk_class == RiskClass.SAFE_READONLY


class TestCommandResult:
    """Test suite for CommandResult."""

    def test_to_dict(self):
        from services.command_runner import CommandResult, CommandStatus
        result = CommandResult(
            status=CommandStatus.SUCCESS,
            output='test output',
            command='test cmd',
            duration=1.5,
        )
        d = result.to_dict()
        assert d['status'] == 'success'
        assert d['output'] == 'test output'
        assert d['duration'] == 1.5
        assert 'operation_id' in d

    def test_is_success(self):
        from services.command_runner import CommandResult, CommandStatus
        r = CommandResult(status=CommandStatus.SUCCESS)
        assert r.is_success
        assert not r.is_error

    def test_is_error(self):
        from services.command_runner import CommandResult, CommandStatus
        r = CommandResult(status=CommandStatus.ERROR)
        assert r.is_error
        assert not r.is_success


class TestPersistence:
    """Test suite for SQLite persistence layer."""

    def test_init_db(self):
        from core.persistence import init_db
        init_db()  # Should not raise

    def test_session_lifecycle(self):
        from core.persistence import init_db, SessionStore
        init_db()
        SessionStore.create('test-session', 'testhost', 'testuser', True)
        s = SessionStore.get('test-session')
        assert s is not None
        assert s['hostname'] == 'testhost'
        SessionStore.close('test-session')
        s = SessionStore.get('test-session')
        assert s['ended_at'] is not None

    def test_audit_log(self):
        from core.persistence import init_db, AuditStore
        init_db()
        AuditStore.log(
            session_id='test-session',
            module='test',
            action='test action',
            status='success',
        )
        entries = AuditStore.get_entries('test-session')
        assert len(entries) >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
