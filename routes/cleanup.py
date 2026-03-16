"""Cleanup routes - ALL mutating endpoints governed via execute_governed_action."""
from flask import Blueprint, render_template, jsonify, request

from services import cleanup as cleanup_svc
from core.governance import execute_governed_action

cleanup_bp = Blueprint('cleanup', __name__)


@cleanup_bp.route('/')
def index():
    return render_template('cleanup.html')


# --- Read-only diagnostics (no governance needed) ---

@cleanup_bp.route('/api/analyze-fragmentation')
def api_analyze_frag():
    result = cleanup_svc.analyze_fragmentation()
    return jsonify(result.to_dict())


# --- Mutating endpoints - ALL go through governance layer ---

@cleanup_bp.route('/api/user-temp', methods=['POST'])
def api_clean_user_temp():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.user_temp', cleanup_svc.clean_user_temp,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/windows-temp', methods=['POST'])
def api_clean_windows_temp():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.windows_temp', cleanup_svc.clean_windows_temp,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/software-distribution', methods=['POST'])
def api_clean_software_dist():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.software_dist', cleanup_svc.clean_software_distribution,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/inet-cache', methods=['POST'])
def api_clean_inet_cache():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.inet_cache', cleanup_svc.clean_inet_cache,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/recycle-bin', methods=['POST'])
def api_empty_recycle_bin():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.recycle_bin', cleanup_svc.empty_recycle_bin,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/dns-cache', methods=['POST'])
def api_flush_dns():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.dns_cache', cleanup_svc.flush_dns_cache,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/cleanmgr', methods=['POST'])
def api_cleanmgr():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.cleanmgr', cleanup_svc.run_cleanmgr,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/component-cleanup', methods=['POST'])
def api_component_cleanup():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.component_cleanup', cleanup_svc.dism_component_cleanup,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/restart-explorer', methods=['POST'])
def api_restart_explorer():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.restart_explorer', cleanup_svc.restart_explorer,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/retrim', methods=['POST'])
def api_retrim():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.retrim', cleanup_svc.retrim_ssd,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/defrag', methods=['POST'])
def api_defrag():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.defrag', cleanup_svc.defrag_hdd,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/scan-duplicates', methods=['POST'])
def api_scan_duplicates():
    data = request.get_json(silent=True) or {}
    directory = data.get('directory')

    def handler():
        return cleanup_svc.scan_duplicate_files(directory)

    result = execute_governed_action(
        'cleanup.scan_duplicates', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/prefetch', methods=['POST'])
def api_clean_prefetch():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.prefetch', cleanup_svc.clean_prefetch,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@cleanup_bp.route('/api/store-cache', methods=['POST'])
def api_store_cache():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'cleanup.store_cache', cleanup_svc.reset_windows_store_cache,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
