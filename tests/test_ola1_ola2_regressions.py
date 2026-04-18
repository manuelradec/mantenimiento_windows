"""
Regression tests for Ola 1 + Ola 2 fixes.

Covers the production incidents reported in staging logs:

1. Allowlist parser must accept quoted Windows paths with spaces, and the
   Lenovo Update flow must reach its binaries without broadening the
   ``start`` allowlist.

2. Security middleware must return JSON — not an HTML error page — when
   an XHR / fetch / API request is rejected by CSRF, Origin, or Host
   validation. The frontend tried to ``JSON.parse`` those responses and
   crashed with "Unexpected token '<'".

3. ``PolicyEngine.get_status()`` preserves its legacy
   ``active_locks`` contract ({module: job_id_str}) while exposing
   detailed metadata under a separate key.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.command_runner import (
    _validate_command,
    _prepare_command,
    _strip_outer_quotes,
)
from core.policy_engine import PolicyEngine


# ============================================================
# 1. Allowlist parser — quoted paths + Lenovo direct launch
# ============================================================

class TestAllowlistQuotedPaths:
    """Regression for the Lenovo Update launch bug."""

    def test_strip_outer_quotes_removes_paired_double_quotes(self):
        assert _strip_outer_quotes('"hello"') == 'hello'
        assert _strip_outer_quotes('""') == ''
        assert _strip_outer_quotes('no-quotes') == 'no-quotes'
        assert _strip_outer_quotes('"mismatched') == '"mismatched'

    def test_prepare_command_keeps_quoted_path_as_single_token(self):
        """Quoted paths must tokenise into a single argv element so the
        allowlist sees the real binary name in cmd_parts[0]."""
        cmd = r'"C:\Program Files (x86)\Lenovo\System Update\tvsu.exe"'
        _actual, _shell, parts = _prepare_command(cmd, powershell=False, shell=False)
        assert parts is not None
        assert len(parts) == 1
        assert parts[0].lower() == (
            r'c:\program files (x86)\lenovo\system update\tvsu.exe'
        )

    def test_lenovo_tvsu_direct_launch_is_allowed(self):
        """Direct launch of tvsu.exe via its full path must pass the
        allowlist (max_args=0 allows only the executable itself)."""
        parts = [r'C:\Program Files (x86)\Lenovo\System Update\tvsu.exe']
        assert _validate_command(parts) is True

    def test_lenovo_vantage_direct_launch_is_allowed(self):
        parts = [r'C:\Program Files (x86)\Lenovo\VantageService\Lenovo.Vantage.exe']
        assert _validate_command(parts) is True

    def test_lenovo_tvsu_rejects_extra_args(self):
        """max_args=0 must block any attempt to pass extra arguments
        to the Lenovo launcher, keeping the surface area minimal."""
        parts = [
            r'C:\Program Files (x86)\Lenovo\System Update\tvsu.exe',
            '/silent',
        ]
        assert _validate_command(parts) is False

    def test_start_allowlist_not_broadened(self):
        """Preserve strict 'start' allowlist: only explorer.exe and
        ms-settings:* are permitted — Lenovo binaries must NOT be
        reachable via 'start', only by direct invocation."""
        assert _validate_command(['start', 'explorer.exe']) is True
        assert _validate_command(['start', 'ms-settings:display']) is True
        # Any attempt to launch a Lenovo binary via 'start' stays blocked.
        parts = [
            'start', '',
            r'C:\Program Files (x86)\Lenovo\System Update\tvsu.exe',
        ]
        assert _validate_command(parts) is False


# ============================================================
# 2. Security middleware — JSON error responses for XHR/fetch
# ============================================================

@pytest.fixture
def flask_client():
    """Minimal Flask app wired with just the security middleware."""
    from flask import Flask
    from core.security import init_security

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['ENVIRONMENT'] = 'local'

    @app.route('/api/echo', methods=['POST'])
    def echo():  # pragma: no cover - only reached on the success path
        from flask import request, jsonify
        return jsonify({'ok': True, 'got': request.get_json(silent=True)})

    init_security(app)
    return app.test_client()


class TestJsonErrorResponses:
    """Regression for 'Unexpected token <' in the browser console."""

    def test_csrf_failure_returns_json_for_xhr(self, flask_client):
        """An AJAX POST without a CSRF token must get JSON back, not HTML."""
        resp = flask_client.post(
            '/api/echo',
            json={'hello': 'world'},
            headers={
                'Origin': 'http://127.0.0.1:5000',
                'Host': '127.0.0.1:5000',
                'X-Requested-With': 'XMLHttpRequest',
            },
        )
        assert resp.status_code == 403
        assert resp.content_type.startswith('application/json')
        payload = resp.get_json()
        assert payload is not None
        assert payload.get('status') == 'error'
        assert payload.get('code') == 403
        assert isinstance(payload.get('error'), str)

    def test_invalid_host_returns_json_for_api_path(self, flask_client):
        resp = flask_client.post(
            '/api/echo',
            json={'x': 1},
            headers={'Host': 'attacker.example.com'},
        )
        assert resp.status_code == 403
        # /api/ path triggers JSON preference regardless of Accept header.
        assert resp.content_type.startswith('application/json')
        assert resp.get_json().get('code') == 403


# ============================================================
# 3. PolicyEngine.get_status() contract + lock helpers
# ============================================================

class TestPolicyEngineContract:

    def test_get_status_active_locks_legacy_shape(self):
        """active_locks must remain a {module: job_id_str} map so
        existing consumers keep working unchanged."""
        p = PolicyEngine()
        p.acquire_lock('repair', 'job-abc')
        status = p.get_status()
        assert status['active_locks'] == {'repair': 'job-abc'}
        assert isinstance(status['active_locks']['repair'], str)
        p.release_lock('repair')

    def test_get_status_exposes_detailed_locks_separately(self):
        """Detailed metadata lives under a NEW key so the legacy
        payload shape is never mutated."""
        p = PolicyEngine()
        p.acquire_lock('repair', 'job-abc')
        status = p.get_status()
        detailed = status['active_locks_detailed']['repair']
        assert detailed['job_id'] == 'job-abc'
        assert 'acquired_at' in detailed
        assert detailed['age_seconds'] >= 0
        p.release_lock('repair')

    def test_get_status_keys_are_additive_not_breaking(self):
        """The legacy key is still present and detailed key is also
        present — no existing key was renamed or removed."""
        p = PolicyEngine()
        status = p.get_status()
        assert 'mode' in status
        assert 'active_locks' in status
        assert 'active_locks_detailed' in status
        assert 'allowed_risk_classes' in status

    def test_force_release_returns_previous_entry(self):
        p = PolicyEngine()
        p.acquire_lock('cleanup', 'stuck-job')
        prev = p.force_release_lock('cleanup')
        assert prev is not None
        assert prev['job_id'] == 'stuck-job'
        # Second call is a no-op.
        assert p.force_release_lock('cleanup') is None

    def test_release_lock_returns_boolean(self):
        p = PolicyEngine()
        assert p.release_lock('missing') is False
        p.acquire_lock('network', 'job-1')
        assert p.release_lock('network') is True
