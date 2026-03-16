"""Security and antivirus routes - ALL mutating endpoints governed."""
from flask import Blueprint, render_template, jsonify, request

from services import antivirus_tools as av_svc
from services import smart_app_control as sac_svc
from core.governance import execute_governed_action

security_bp = Blueprint('security', __name__)


@security_bp.route('/')
def index():
    return render_template('security.html')


# --- Read-only ---

@security_bp.route('/api/overview')
def api_overview():
    return jsonify(av_svc.get_security_overview())


@security_bp.route('/api/defender-status')
def api_defender_status():
    return jsonify(av_svc.get_defender_status().to_dict())


@security_bp.route('/api/defender-config')
def api_defender_config():
    return jsonify(av_svc.get_defender_config().to_dict())


@security_bp.route('/api/third-party')
def api_third_party():
    return jsonify(av_svc.detect_third_party_antivirus().to_dict())


# --- Mutating endpoints - ALL governed ---

@security_bp.route('/api/quick-scan', methods=['POST'])
def api_quick_scan():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'security.quick_scan', av_svc.defender_quick_scan,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@security_bp.route('/api/full-scan', methods=['POST'])
def api_full_scan():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'security.full_scan', av_svc.defender_full_scan,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@security_bp.route('/api/set-cpu-load', methods=['POST'])
def api_set_cpu_load():
    data = request.get_json(silent=True) or {}
    factor = int(data.get('factor', 50))

    def handler():
        return av_svc.set_defender_cpu_load(factor)

    result = execute_governed_action(
        'security.set_cpu_load', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@security_bp.route('/api/update-signatures', methods=['POST'])
def api_update_sigs():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'security.update_signatures', av_svc.update_defender_signatures,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


# --- Smart App Control (Control Inteligente de Aplicaciones) ---

@security_bp.route('/api/smart-app-control/status')
def api_sac_status():
    """Read-only: detect Smart App Control state."""
    return jsonify(sac_svc.detect_smart_app_control_status().to_dict())


@security_bp.route('/api/smart-app-control/disable', methods=['POST'])
def api_sac_disable():
    """Governed: attempt to disable Smart App Control (DESTRUCTIVE)."""
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'security.disable_sac', sac_svc.attempt_disable_smart_app_control,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@security_bp.route('/api/smart-app-control/open-settings', methods=['POST'])
def api_sac_open_settings():
    """Governed: open Windows Security SAC settings page."""
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'security.open_sac_settings', sac_svc.open_smart_app_control_settings,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
