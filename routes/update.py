"""Windows Update routes."""
from flask import Blueprint, render_template, jsonify

from services import windows_update as wu_svc
from services.reports import get_log

update_bp = Blueprint('update', __name__)


@update_bp.route('/')
def index():
    return render_template('update.html')


@update_bp.route('/api/scan', methods=['POST'])
def api_scan():
    result = wu_svc.scan_updates()
    get_log().add_entry('update', 'Scan updates', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@update_bp.route('/api/download', methods=['POST'])
def api_download():
    result = wu_svc.download_updates()
    get_log().add_entry('update', 'Download updates', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@update_bp.route('/api/install', methods=['POST'])
def api_install():
    result = wu_svc.install_updates()
    get_log().add_entry('update', 'Install updates', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@update_bp.route('/api/services')
def api_services():
    return jsonify(wu_svc.get_update_services_status().to_dict())


@update_bp.route('/api/open-settings', methods=['POST'])
def api_open_settings():
    result = wu_svc.open_windows_update_settings()
    return jsonify(result.to_dict())


@update_bp.route('/api/hard-reset', methods=['POST'])
def api_hard_reset():
    results = wu_svc.hard_reset_windows_update()
    get_log().add_entry('update', 'Hard reset Windows Update', 'success',
                        result='Hard reset sequence completed')
    return jsonify(results)


@update_bp.route('/api/resync-time', methods=['POST'])
def api_resync_time():
    results = wu_svc.resync_time()
    get_log().add_entry('update', 'Resync system time', 'success',
                        result='Time sync completed')
    return jsonify(results)
