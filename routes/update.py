"""Windows Update routes - ALL mutating endpoints governed."""
from flask import Blueprint, render_template, jsonify, request

from services import windows_update as wu_svc
from core.governance import execute_governed_action

update_bp = Blueprint('update', __name__)


@update_bp.route('/')
def index():
    return render_template('update.html')


# --- Read-only ---

@update_bp.route('/api/services')
def api_services():
    return jsonify(wu_svc.get_update_services_status().to_dict())


# --- Mutating endpoints - ALL governed ---

@update_bp.route('/api/scan', methods=['POST'])
def api_scan():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.scan', wu_svc.scan_updates,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@update_bp.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.download', wu_svc.download_updates,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@update_bp.route('/api/install', methods=['POST'])
def api_install():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.install', wu_svc.install_updates,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@update_bp.route('/api/open-settings', methods=['POST'])
def api_open_settings():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.open_settings', wu_svc.open_windows_update_settings,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@update_bp.route('/api/hard-reset', methods=['POST'])
def api_hard_reset():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.hard_reset', wu_svc.hard_reset_windows_update,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@update_bp.route('/api/resync-time', methods=['POST'])
def api_resync_time():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'update.resync_time', wu_svc.resync_time,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
