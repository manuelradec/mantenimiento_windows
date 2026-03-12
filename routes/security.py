"""Security and antivirus routes."""
from flask import Blueprint, render_template, jsonify, request

from services import antivirus_tools as av_svc
from services.reports import get_log

security_bp = Blueprint('security', __name__)


@security_bp.route('/')
def index():
    return render_template('security.html')


@security_bp.route('/api/overview')
def api_overview():
    return jsonify(av_svc.get_security_overview())


@security_bp.route('/api/quick-scan', methods=['POST'])
def api_quick_scan():
    result = av_svc.defender_quick_scan()
    get_log().add_entry('security', 'Defender quick scan', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@security_bp.route('/api/full-scan', methods=['POST'])
def api_full_scan():
    result = av_svc.defender_full_scan()
    get_log().add_entry('security', 'Defender full scan', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@security_bp.route('/api/defender-status')
def api_defender_status():
    return jsonify(av_svc.get_defender_status().to_dict())


@security_bp.route('/api/defender-config')
def api_defender_config():
    return jsonify(av_svc.get_defender_config().to_dict())


@security_bp.route('/api/set-cpu-load', methods=['POST'])
def api_set_cpu_load():
    data = request.get_json(silent=True) or {}
    factor = data.get('factor', 50)
    result = av_svc.set_defender_cpu_load(int(factor))
    get_log().add_entry('security', f'Set Defender CPU load to {factor}%',
                        result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@security_bp.route('/api/update-signatures', methods=['POST'])
def api_update_sigs():
    result = av_svc.update_defender_signatures()
    get_log().add_entry('security', 'Update Defender signatures', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@security_bp.route('/api/third-party')
def api_third_party():
    return jsonify(av_svc.detect_third_party_antivirus().to_dict())
