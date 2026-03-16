"""Repair routes - ALL mutating endpoints governed via execute_governed_action."""
from flask import Blueprint, render_template, jsonify, request

from services import repair as repair_svc
from core.governance import execute_governed_action

repair_bp = Blueprint('repair', __name__)


@repair_bp.route('/')
def index():
    return render_template('repair.html')


@repair_bp.route('/api/sfc', methods=['POST'])
def api_sfc():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.sfc', repair_svc.run_sfc_scan,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/dism-check', methods=['POST'])
def api_dism_check():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.dism_check', repair_svc.dism_check_health,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/dism-scan', methods=['POST'])
def api_dism_scan():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.dism_scan', repair_svc.dism_scan_health,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/dism-restore', methods=['POST'])
def api_dism_restore():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.dism_restore', repair_svc.dism_restore_health,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/component-cleanup', methods=['POST'])
def api_component_cleanup():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.component_cleanup', repair_svc.dism_component_cleanup,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/chkdsk-scan', methods=['POST'])
def api_chkdsk_scan():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.chkdsk_scan', repair_svc.chkdsk_scan_online,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/chkdsk-schedule', methods=['POST'])
def api_chkdsk_schedule():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.chkdsk_schedule', repair_svc.chkdsk_schedule_full,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/winsat', methods=['POST'])
def api_winsat():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.winsat', repair_svc.winsat_disk,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/memory-diagnostic', methods=['POST'])
def api_memory_diag():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.memory_diagnostic', repair_svc.schedule_memory_diagnostic,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@repair_bp.route('/api/full-sequence', methods=['POST'])
def api_full_sequence():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'repair.full_sequence', repair_svc.run_repair_sequence,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
