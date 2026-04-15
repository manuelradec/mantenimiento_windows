"""Windows Features routes — shared-folder troubleshooting + optional features (Phase 4–5)."""
from flask import Blueprint, render_template, jsonify, request

from services import windows_features as wf_svc
from services import smb_repair as smb_svc
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


# --- Phase 5: optional features ---

@windows_features_bp.route('/api/optional-features')
def api_optional_features():
    """Return current state of optional Windows features (read-only)."""
    return jsonify(wf_svc.get_optional_features_status())


@windows_features_bp.route('/api/enable-dotnet35', methods=['POST'])
def api_enable_dotnet35():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'windows_features.enable_dotnet35',
        wf_svc.enable_dotnet35,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/enable-dotnet48-adv', methods=['POST'])
def api_enable_dotnet48_adv():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'windows_features.enable_dotnet48_adv',
        wf_svc.enable_dotnet48_adv,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/enable-smb1', methods=['POST'])
def api_enable_smb1():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'windows_features.enable_smb1',
        wf_svc.enable_smb1,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# SMB Repair Workflow — read-only diagnostics (no governance needed)
# ---------------------------------------------------------------------------

@windows_features_bp.route('/api/smb/check-services')
def api_smb_check_services():
    """Check LanmanServer, LanmanWorkstation, lmhosts service states."""
    return jsonify(smb_svc.check_smb_services())


@windows_features_bp.route('/api/smb/client-config')
def api_smb_client_config():
    """Return Get-SmbClientConfiguration key security parameters."""
    return jsonify(smb_svc.get_smb_client_config())


@windows_features_bp.route('/api/smb/mapped-drives')
def api_smb_mapped_drives():
    """List currently mapped network drives."""
    return jsonify(smb_svc.get_mapped_drives())


@windows_features_bp.route('/api/smb/test-reachability', methods=['POST'])
def api_smb_test_reachability():
    """Test ping + TCP 445 reachability for a given host."""
    data = request.get_json(silent=True) or {}
    host = str(data.get('host', '')).strip()
    return jsonify(smb_svc.test_host_reachability(host))


@windows_features_bp.route('/api/smb/test-unc-access', methods=['POST'])
def api_smb_test_unc_access():
    """Attempt Get-ChildItem on a UNC path to capture the real SMB error."""
    data = request.get_json(silent=True) or {}
    unc_path = str(data.get('unc_path', '')).strip()
    return jsonify(smb_svc.test_unc_access(unc_path))


@windows_features_bp.route('/api/smb/run-full-diagnosis', methods=['POST'])
def api_smb_run_full_diagnosis():
    """
    Orchestrate all read-only SMB diagnostics and return classification.

    Body: {host?: str, unc_path?: str}
    """
    data = request.get_json(silent=True) or {}
    host = str(data.get('host', '')).strip()
    unc_path = str(data.get('unc_path', '')).strip()
    return jsonify(smb_svc.run_full_smb_diagnosis(host=host, unc_path=unc_path))


# ---------------------------------------------------------------------------
# SMB Repair Workflow — mutating actions (ALL governed)
# ---------------------------------------------------------------------------

@windows_features_bp.route('/api/smb/map-drive', methods=['POST'])
def api_smb_map_drive():
    """Map a network share to a drive letter."""
    data = request.get_json(silent=True) or {}
    drive_letter = str(data.get('drive_letter', '')).strip()
    unc_path = str(data.get('unc_path', '')).strip()

    def handler():
        return smb_svc.map_drive(drive_letter, unc_path)

    result = execute_governed_action(
        'smb.map_drive', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/smb/clear-sessions', methods=['POST'])
def api_smb_clear_sessions():
    """Remove all mapped drives and SMB session cache (net use * /delete)."""
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'smb.clear_sessions', smb_svc.clear_smb_sessions,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/smb/disable-require-signing', methods=['POST'])
def api_smb_disable_require_signing():
    """
    Disable RequireSecuritySignature on the SMB client.

    Primary fix for the confirmed incident pattern:
    'configured to require SMB signing'.
    Preserves EnableSecuritySignature = True.
    """
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'smb.disable_require_signing', smb_svc.disable_require_signing,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/smb/restart-lanman', methods=['POST'])
def api_smb_restart_lanman():
    """Restart LanmanWorkstation (SMB client) service."""
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'smb.restart_lanman', smb_svc.restart_lanman_workstation,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@windows_features_bp.route('/api/smb/allow-insecure-guest', methods=['POST'])
def api_smb_allow_insecure_guest():
    """
    Enable insecure guest logons via registry (legacy compatibility only).

    NOT the default fix. Requires EXPERT mode (DESTRUCTIVE risk class).
    """
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'smb.allow_insecure_guest', smb_svc.allow_insecure_guest,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
