"""Diagnostics routes."""
from flask import Blueprint, render_template, jsonify

from services import system_info

diagnostics_bp = Blueprint('diagnostics', __name__)


@diagnostics_bp.route('/')
def index():
    return render_template('diagnostics.html')


@diagnostics_bp.route('/api/full')
def api_full_diagnostics():
    return jsonify(system_info.run_full_diagnostics())


@diagnostics_bp.route('/api/system-overview')
def api_system_overview():
    return jsonify(system_info.get_system_overview())


@diagnostics_bp.route('/api/windows-version')
def api_windows_version():
    return jsonify(system_info.get_windows_version().to_dict())


@diagnostics_bp.route('/api/ram')
def api_ram():
    return jsonify(system_info.get_ram_details().to_dict())


@diagnostics_bp.route('/api/disks')
def api_disks():
    return jsonify(system_info.get_disk_details().to_dict())


@diagnostics_bp.route('/api/smart')
def api_smart():
    return jsonify(system_info.get_smart_status().to_dict())


@diagnostics_bp.route('/api/trim')
def api_trim():
    return jsonify(system_info.get_trim_status().to_dict())


@diagnostics_bp.route('/api/display-events')
def api_display_events():
    return jsonify(system_info.get_display_events().to_dict())


@diagnostics_bp.route('/api/top-processes')
def api_top_processes():
    return jsonify(system_info.get_top_processes().to_dict())


@diagnostics_bp.route('/api/services')
def api_services():
    return jsonify(system_info.get_important_services().to_dict())


@diagnostics_bp.route('/api/drivers')
def api_drivers():
    return jsonify(system_info.get_driver_list().to_dict())


@diagnostics_bp.route('/api/problem-devices')
def api_problem_devices():
    return jsonify(system_info.get_problem_devices().to_dict())


@diagnostics_bp.route('/api/network')
def api_network():
    return jsonify(system_info.get_network_overview().to_dict())


@diagnostics_bp.route('/api/routes')
def api_routes():
    return jsonify(system_info.get_route_table().to_dict())


@diagnostics_bp.route('/api/startup')
def api_startup():
    return jsonify(system_info.get_startup_programs().to_dict())


@diagnostics_bp.route('/api/remote-access')
def api_remote_access():
    return jsonify(system_info.detect_remote_access_processes().to_dict())


@diagnostics_bp.route('/api/temperature')
def api_temperature():
    return jsonify(system_info.get_temperature().to_dict())


@diagnostics_bp.route('/api/license')
def api_license():
    return jsonify(system_info.get_license_status().to_dict())


@diagnostics_bp.route('/api/time-sync')
def api_time_sync():
    return jsonify(system_info.get_time_sync_status().to_dict())
