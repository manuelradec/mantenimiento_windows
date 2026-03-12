"""Repair routes."""
from flask import Blueprint, render_template, jsonify

from services import repair as repair_svc
from services.reports import get_log

repair_bp = Blueprint('repair', __name__)


@repair_bp.route('/')
def index():
    return render_template('repair.html')


@repair_bp.route('/api/sfc', methods=['POST'])
def api_sfc():
    result = repair_svc.run_sfc_scan()
    get_log().add_entry('repair', 'SFC /scannow', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/dism-check', methods=['POST'])
def api_dism_check():
    result = repair_svc.dism_check_health()
    get_log().add_entry('repair', 'DISM CheckHealth', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/dism-scan', methods=['POST'])
def api_dism_scan():
    result = repair_svc.dism_scan_health()
    get_log().add_entry('repair', 'DISM ScanHealth', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/dism-restore', methods=['POST'])
def api_dism_restore():
    result = repair_svc.dism_restore_health()
    get_log().add_entry('repair', 'DISM RestoreHealth', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/component-cleanup', methods=['POST'])
def api_component_cleanup():
    result = repair_svc.dism_component_cleanup()
    get_log().add_entry('repair', 'DISM ComponentCleanup', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/chkdsk-scan', methods=['POST'])
def api_chkdsk_scan():
    result = repair_svc.chkdsk_scan_online()
    get_log().add_entry('repair', 'CHKDSK online scan', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/chkdsk-schedule', methods=['POST'])
def api_chkdsk_schedule():
    result = repair_svc.chkdsk_schedule_full()
    get_log().add_entry('repair', 'Schedule full CHKDSK', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/winsat', methods=['POST'])
def api_winsat():
    result = repair_svc.winsat_disk()
    get_log().add_entry('repair', 'WinSAT disk', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/memory-diagnostic', methods=['POST'])
def api_memory_diag():
    result = repair_svc.schedule_memory_diagnostic()
    get_log().add_entry('repair', 'Memory Diagnostic', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@repair_bp.route('/api/full-sequence', methods=['POST'])
def api_full_sequence():
    results = repair_svc.run_repair_sequence()
    get_log().add_entry('repair', 'Full repair sequence', 'success',
                        result='Sequence completed')
    return jsonify(results)
