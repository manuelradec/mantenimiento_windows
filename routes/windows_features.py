"""Windows Features routes — shared-folder guided troubleshooting (Phase 4)."""
from flask import Blueprint, render_template, jsonify, request

from services import windows_features as wf_svc
from core.governance import execute_governed_action

windows_features_bp = Blueprint('windows_features', __name__)


@windows_features_bp.route('/')
def index():
    return render_template('windows_features.html')


# --- Read-only ---

@windows_features_bp.route('/api/shared-folder-diag')
def api_shared_folder_diag():
    """Return comprehensive shared-folder diagnostic (read-only)."""
    return jsonify(wf_svc.run_shared_folder_diagnostics())


# --- Mutating endpoints — ALL governed ---

@windows_features_bp.route('/api/test-unc', methods=['POST'])
def api_test_unc():
    """Test TCP 445 connectivity to the server in a given UNC path."""
    data = request.get_json(silent=True) or {}
    unc_path = str(data.get('unc_path', '')).strip()

    def handler():
        return wf_svc.test_unc_connectivity(unc_path)

    result = execute_governed_action(
        'windows_features.test_unc', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/open-network-path', methods=['POST'])
def api_open_network_path():
    """Open a validated UNC path in Windows Explorer."""
    data = request.get_json(silent=True) or {}
    unc_path = str(data.get('unc_path', '')).strip()

    def handler():
        return wf_svc.open_network_path(unc_path)

    result = execute_governed_action(
        'windows_features.open_network_path', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
