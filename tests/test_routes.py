"""Tests for Flask routes - CSRF, governance, read-only vs mutating."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app(tmp_path):
    """Create test application with temp dirs to avoid PermissionError."""
    import config as cfg
    # Override log/report dirs to temp before importing create_app
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
    """Create test client."""
    return app.test_client()


def _get_csrf_token(client):
    """Get a valid CSRF token by making a GET request."""
    response = client.get('/')
    # Extract CSRF token from session
    with client.session_transaction() as sess:
        return sess.get('csrf_token', '')


class TestReadOnlyRoutes:
    """Test that all GET/read-only endpoints work without CSRF."""

    def test_dashboard_loads(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_diagnostics_page(self, client):
        resp = client.get('/diagnostics/')
        assert resp.status_code == 200

    def test_cleanup_page(self, client):
        resp = client.get('/cleanup/')
        assert resp.status_code == 200

    def test_repair_page(self, client):
        resp = client.get('/repair/')
        assert resp.status_code == 200

    def test_network_page(self, client):
        resp = client.get('/network/')
        assert resp.status_code == 200

    def test_update_page(self, client):
        resp = client.get('/update/')
        assert resp.status_code == 200

    def test_power_page(self, client):
        resp = client.get('/power/')
        assert resp.status_code == 200

    def test_security_page(self, client):
        resp = client.get('/security/')
        assert resp.status_code == 200

    def test_reports_page(self, client):
        resp = client.get('/reports/')
        assert resp.status_code == 200

    def test_advanced_page(self, client):
        resp = client.get('/advanced/')
        assert resp.status_code == 200

    def test_drivers_page(self, client):
        resp = client.get('/drivers/')
        assert resp.status_code == 200

    def test_api_system_overview(self, client):
        resp = client.get('/api/system-overview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'os_name' in data

    def test_api_elevation(self, client):
        resp = client.get('/api/elevation')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'is_admin' in data

    def test_api_policy_status(self, client):
        resp = client.get('/api/policy/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'mode' in data

    def test_api_actions_list(self, client):
        resp = client.get('/api/actions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) > 30  # Should have many registered actions

    def test_api_allowed_actions(self, client):
        resp = client.get('/api/actions/allowed')
        assert resp.status_code == 200

    def test_api_jobs_list(self, client):
        resp = client.get('/api/jobs')
        assert resp.status_code == 200

    def test_route_registration(self, app):
        """All expected blueprints should be registered."""
        blueprints = list(app.blueprints.keys())
        expected = ['dashboard', 'diagnostics', 'cleanup', 'repair',
                    'network', 'update', 'power', 'drivers', 'security',
                    'reports', 'advanced']
        for bp in expected:
            assert bp in blueprints, f"Blueprint '{bp}' not registered"


class TestCSRFProtection:
    """Test CSRF token enforcement on mutating endpoints."""

    def test_post_without_csrf_is_rejected(self, client):
        """POST without CSRF token should return 403."""
        resp = client.post('/cleanup/api/user-temp',
                          headers={'Origin': 'http://127.0.0.1:5000'},
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 403

    def test_post_with_valid_csrf_succeeds(self, client):
        """POST with valid CSRF token should pass CSRF check."""
        csrf = _get_csrf_token(client)
        resp = client.post('/cleanup/api/user-temp',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}')
        # Should not be 403 (CSRF pass). May be 200 or other based on governance.
        assert resp.status_code != 403

    def test_post_with_wrong_csrf_is_rejected(self, client):
        """POST with wrong CSRF token should return 403."""
        _get_csrf_token(client)  # establish session
        resp = client.post('/cleanup/api/user-temp',
                          headers={
                              'X-CSRF-Token': 'wrong-token',
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 403


class TestOriginValidation:
    """Test Origin/Referer header enforcement."""

    def test_post_with_invalid_origin_rejected(self, client):
        """POST from external origin should be blocked."""
        csrf = _get_csrf_token(client)
        resp = client.post('/cleanup/api/user-temp',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://evil.com',
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 403

    def test_post_with_no_origin_no_referer_rejected(self, client):
        """POST with neither Origin nor Referer should be blocked."""
        csrf = _get_csrf_token(client)
        resp = client.post('/cleanup/api/user-temp',
                          headers={
                              'X-CSRF-Token': csrf,
                              # No Origin or Referer
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code == 403

    def test_post_with_valid_referer_succeeds(self, client):
        """POST with valid Referer should pass origin check."""
        csrf = _get_csrf_token(client)
        resp = client.post('/cleanup/api/user-temp',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Referer': 'http://127.0.0.1:5000/cleanup/',
                          },
                          content_type='application/json',
                          data='{}')
        assert resp.status_code != 403


class TestHostValidation:
    """Test Host header validation."""

    def test_request_with_valid_host(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_request_with_invalid_host(self, client):
        resp = client.get('/', headers={'Host': 'evil.com:5000'})
        assert resp.status_code == 403


class TestGovernedEndpoints:
    """Test that mutating endpoints go through governance and return proper structures."""

    def _post_governed(self, client, url, data=None):
        csrf = _get_csrf_token(client)
        return client.post(url,
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}' if data is None else data)

    def test_cleanup_endpoint_returns_governed_result(self, client):
        resp = self._post_governed(client, '/cleanup/api/user-temp')
        assert resp.status_code == 200
        data = resp.get_json()
        # Should have governance fields
        assert 'status' in data
        assert 'action_id' in data or data.get('status') in ('rejected', 'needs_confirmation', 'not_applicable')

    def test_network_flush_dns_governed(self, client):
        resp = self._post_governed(client, '/network/api/flush-dns')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'status' in data

    def test_repair_sfc_governed(self, client):
        """SFC is RISKY - should be rejected in default safe_maintenance mode."""
        resp = self._post_governed(client, '/repair/api/sfc')
        assert resp.status_code == 200
        data = resp.get_json()
        # In safe_maintenance mode, RISKY actions should be rejected
        assert data.get('status') in ('rejected', 'not_applicable')

    def test_update_scan_governed(self, client):
        resp = self._post_governed(client, '/update/api/scan')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'status' in data

    def test_power_set_balanced_governed(self, client):
        """Set balanced is DISRUPTIVE - blocked in safe_maintenance mode."""
        resp = self._post_governed(client, '/power/api/set-balanced')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') in ('rejected', 'not_applicable')

    def test_mode_change_enables_advanced(self, client):
        """After switching to advanced mode, RISKY actions should be allowed."""
        csrf = _get_csrf_token(client)
        # Change to advanced mode
        client.post('/api/policy/mode',
                    headers={
                        'X-CSRF-Token': csrf,
                        'Origin': 'http://127.0.0.1:5000',
                    },
                    content_type='application/json',
                    data='{"mode": "advanced"}')

        # Now RISKY actions should pass policy (may still need confirmation)
        resp = client.post('/repair/api/dism-check',
                          headers={
                              'X-CSRF-Token': csrf,
                              'Origin': 'http://127.0.0.1:5000',
                          },
                          content_type='application/json',
                          data='{}')
        data = resp.get_json()
        # Should not be rejected for mode_restriction
        assert data.get('status') != 'rejected' or 'mode' not in data.get('reason', '')


class TestSecurityHeaders:
    """Test that security headers are properly set."""

    def test_csp_header(self, client):
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert 'frame-ancestors' in csp
        assert "default-src 'self'" in csp

    def test_x_frame_options(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_nosniff(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy(self, client):
        resp = client.get('/')
        assert resp.headers.get('Referrer-Policy') == 'same-origin'

    def test_no_cache(self, client):
        resp = client.get('/')
        assert 'no-store' in resp.headers.get('Cache-Control', '')
