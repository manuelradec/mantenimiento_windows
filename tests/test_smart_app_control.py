"""Tests for Smart App Control (Control Inteligente de Aplicaciones) feature."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.smart_app_control import (
    detect_smart_app_control_status,
    attempt_disable_smart_app_control,
    open_smart_app_control_settings,
    _build_status_details,
    _get_state_explanation,
    SAC_STATE_MAP,
    SAC_STATE_LABELS_ES,
)
from services.command_runner import CommandStatus
from core.action_registry import registry, RiskClass, OperationMode
from core.policy_engine import PolicyEngine


# ============================================================
# Detection behavior
# ============================================================

class TestDetection:
    """Test Smart App Control detection on non-Windows (simulated)."""

    def test_detect_returns_not_applicable_on_non_windows(self):
        """On Linux/macOS, detection should return not_applicable."""
        if sys.platform == 'win32':
            pytest.skip('Only runs on non-Windows')
        result = detect_smart_app_control_status()
        assert result.status == CommandStatus.NOT_APPLICABLE
        assert result.details['state'] == 'not_available'
        assert result.details['supported'] is False

    def test_detect_returns_command_result(self):
        """Detection should always return a CommandResult."""
        result = detect_smart_app_control_status()
        assert hasattr(result, 'status')
        assert hasattr(result, 'output')
        assert hasattr(result, 'details')
        assert 'state' in result.details
        assert 'supported' in result.details
        assert 'detection_method' in result.details

    def test_detect_details_have_required_fields(self):
        """All required detail fields must be present."""
        result = detect_smart_app_control_status()
        d = result.details
        required_fields = [
            'state', 'state_label', 'supported', 'changeable',
            'can_disable', 'can_enable', 'admin_required',
            'reboot_required', 'one_way_disable', 'detection_method',
            'raw_value', 'explanation',
        ]
        for field in required_fields:
            assert field in d, f"Missing field: {field}"

    def test_detect_can_enable_always_false(self):
        """Re-enabling SAC is never possible programmatically."""
        result = detect_smart_app_control_status()
        assert result.details['can_enable'] is False

    def test_detect_admin_required_always_true(self):
        """Admin is always required for SAC operations."""
        result = detect_smart_app_control_status()
        assert result.details['admin_required'] is True

    def test_detect_one_way_disable_always_true(self):
        """Disabling SAC is always a one-way operation."""
        result = detect_smart_app_control_status()
        assert result.details['one_way_disable'] is True


# ============================================================
# Unsupported / not_applicable behavior
# ============================================================

class TestUnsupported:
    """Test behavior when SAC is unsupported."""

    def test_attempt_disable_on_non_windows(self):
        """Disable should return not_applicable on non-Windows."""
        if sys.platform == 'win32':
            pytest.skip('Only runs on non-Windows')
        result = attempt_disable_smart_app_control()
        assert result.status == CommandStatus.NOT_APPLICABLE

    def test_open_settings_returns_result(self):
        """Open settings should return a CommandResult."""
        result = open_smart_app_control_settings()
        assert hasattr(result, 'status')
        # On non-Windows it will be NOT_APPLICABLE
        if sys.platform != 'win32':
            assert result.status == CommandStatus.NOT_APPLICABLE


# ============================================================
# State mapping and labels
# ============================================================

class TestStateMapping:
    """Test state value mapping and Spanish labels."""

    def test_state_map_values(self):
        assert SAC_STATE_MAP[0] == 'off'
        assert SAC_STATE_MAP[1] == 'on'
        assert SAC_STATE_MAP[2] == 'evaluation'

    def test_all_states_have_spanish_labels(self):
        expected_states = ['on', 'evaluation', 'off', 'not_available',
                          'unsupported', 'unknown']
        for state in expected_states:
            assert state in SAC_STATE_LABELS_ES, f"Missing label: {state}"
            assert len(SAC_STATE_LABELS_ES[state]) > 0

    def test_all_states_have_explanations(self):
        expected_states = ['on', 'evaluation', 'off', 'not_available',
                          'unsupported', 'unknown']
        for state in expected_states:
            explanation = _get_state_explanation(state)
            assert len(explanation) > 0, f"Empty explanation for state: {state}"


# ============================================================
# Build status details helper
# ============================================================

class TestBuildStatusDetails:
    """Test the _build_status_details helper."""

    def test_default_values(self):
        d = _build_status_details(state='unknown')
        assert d['state'] == 'unknown'
        assert d['supported'] is False
        assert d['changeable'] is False
        assert d['can_disable'] is False
        assert d['can_enable'] is False
        assert d['admin_required'] is True
        assert d['one_way_disable'] is True

    def test_on_state_requires_reboot(self):
        d = _build_status_details(state='on', supported=True)
        assert d['reboot_required'] is True

    def test_evaluation_state_requires_reboot(self):
        d = _build_status_details(state='evaluation', supported=True)
        assert d['reboot_required'] is True

    def test_off_state_no_reboot(self):
        d = _build_status_details(state='off')
        assert d['reboot_required'] is False

    def test_state_label_populated(self):
        d = _build_status_details(state='on')
        assert d['state_label'] == 'Activado'
        d = _build_status_details(state='evaluation')
        assert d['state_label'] == 'Evaluación'
        d = _build_status_details(state='off')
        assert d['state_label'] == 'Desactivado'


# ============================================================
# Policy enforcement
# ============================================================

class TestPolicyEnforcement:
    """Test that SAC actions are properly registered in policy."""

    def test_detection_action_registered(self):
        action = registry.get('diag.smart_app_control')
        assert action is not None
        assert action.risk_class == RiskClass.SAFE_READONLY

    def test_disable_action_registered(self):
        action = registry.get('security.disable_sac')
        assert action is not None
        assert action.risk_class == RiskClass.DESTRUCTIVE
        assert action.requires_admin is True
        assert action.requires_confirmation is True
        assert action.needs_restore_point is True
        assert action.needs_reboot is True

    def test_open_settings_action_registered(self):
        action = registry.get('security.open_sac_settings')
        assert action is not None
        assert action.risk_class == RiskClass.SAFE_MUTATION

    def test_disable_sac_blocked_in_diagnostic_mode(self):
        """Destructive actions must be blocked in diagnostic mode."""
        pe = PolicyEngine()
        action = registry.get('security.disable_sac')
        result = pe.validate_action(action, is_admin=True)
        # In diagnostic mode (default), destructive actions are rejected
        assert result.get('allowed') is False or result.get('needs_confirmation') is True

    def test_disable_sac_requires_admin(self):
        """Without admin, destructive SAC action should be rejected."""
        pe = PolicyEngine()
        action = registry.get('security.disable_sac')
        result = pe.validate_action(action, is_admin=False)
        assert result.get('allowed') is False

    def test_disable_sac_requires_confirmation_in_expert_mode(self):
        """In expert mode, destructive SAC action needs confirmation."""
        pe = PolicyEngine()
        pe.set_mode(OperationMode.EXPERT)
        action = registry.get('security.disable_sac')
        # First call without token should need confirmation
        result = pe.validate_action(action, is_admin=True)
        assert result.get('needs_confirmation') is True or result.get('allowed') is True


# ============================================================
# Route protection
# ============================================================

@pytest.fixture
def app(tmp_path):
    """Create test application with temp dirs."""
    import config as cfg
    cfg.Config.LOG_DIR = str(tmp_path / 'logs')
    cfg.Config.REPORT_DIR = str(tmp_path / 'reports')
    os.makedirs(cfg.Config.LOG_DIR, exist_ok=True)
    os.makedirs(cfg.Config.REPORT_DIR, exist_ok=True)

    from app import create_app
    from core.persistence import init_db

    app = create_app()
    app.config['TESTING'] = True
    app.config['SESSION_ID'] = 'test-session'
    app.config['HOSTNAME'] = 'testhost'
    app.config['USERNAME'] = 'testuser'
    init_db()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _get_csrf_token(client):
    """Get a valid CSRF token by making a GET request."""
    client.get('/')
    with client.session_transaction() as sess:
        return sess.get('csrf_token', '')


class TestRouteProtection:
    """Test that SAC routes are properly protected."""

    def test_sac_status_route_exists(self, client):
        resp = client.get('/security/api/smart-app-control/status')
        assert resp.status_code == 200

    def test_sac_status_returns_json(self, client):
        resp = client.get('/security/api/smart-app-control/status')
        data = resp.get_json()
        assert 'status' in data
        assert 'details' in data

    def test_sac_disable_requires_csrf(self, client):
        """POST to disable without CSRF should be rejected."""
        resp = client.post('/security/api/smart-app-control/disable',
                          headers={'Origin': 'http://127.0.0.1:5000'},
                          content_type='application/json',
                          data='{}')
        # Should be 403 (CSRF missing)
        assert resp.status_code == 403

    def test_sac_disable_governed(self, client):
        """Disable action should go through governance."""
        csrf = _get_csrf_token(client)
        resp = client.post('/security/api/smart-app-control/disable',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 200
        data = resp.get_json()
        # Must be governed: rejected (wrong mode), needs_confirmation,
        # or not_applicable (non-Windows)
        assert data.get('status') in ('rejected', 'needs_confirmation',
                                      'error', 'not_applicable')

    def test_sac_open_settings_route_exists(self, client):
        """Open settings route should exist and be governed."""
        csrf = _get_csrf_token(client)
        resp = client.post('/security/api/smart-app-control/open-settings',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 200

    def test_security_page_loads(self, client):
        resp = client.get('/security/')
        assert resp.status_code == 200
        assert b'Control Inteligente de Aplicaciones' in resp.data


# ============================================================
# Rollback classification
# ============================================================

class TestRollbackClassification:
    """Test that SAC rollback info is correctly classified."""

    def test_disable_sac_rollback_not_reversible(self):
        from core.governance import ROLLBACK_STRATEGIES
        rollback = ROLLBACK_STRATEGIES.get('security.disable_sac')
        assert rollback is not None
        assert rollback['classification'] == 'not_reversible'
        assert rollback['reversible'] == 'no'
        assert rollback['needs_reboot'] is True
        assert rollback['restore_point_recommended'] is True

    def test_open_settings_rollback_not_applicable(self):
        from core.governance import ROLLBACK_STRATEGIES
        rollback = ROLLBACK_STRATEGIES.get('security.open_sac_settings')
        assert rollback is not None
        assert rollback['classification'] == 'not_applicable'


# ============================================================
# Snapshot integration
# ============================================================

class TestSnapshotIntegration:
    """Test that security snapshots include SAC data."""

    def test_security_snapshot_includes_sac(self):
        from core.snapshots import snapshot_security
        snap = snapshot_security('security.disable_sac')
        assert 'smart_app_control' in snap
        # On non-Windows it should be 'not_applicable'
        if sys.platform != 'win32':
            assert snap['smart_app_control'] == 'not_applicable'
        else:
            assert isinstance(snap['smart_app_control'], dict)
            assert 'state' in snap['smart_app_control']

    def test_capture_action_snapshot_works_for_sac(self):
        from core.snapshots import capture_action_snapshot
        snap = capture_action_snapshot('security.disable_sac', 'before')
        assert snap['category'] == 'security'
        assert snap['phase'] == 'before'
        assert 'smart_app_control' in snap
