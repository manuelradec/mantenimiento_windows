"""Cleanup routes."""
from flask import Blueprint, render_template, jsonify, request

from services import cleanup as cleanup_svc
from services.reports import get_log

cleanup_bp = Blueprint('cleanup', __name__)


@cleanup_bp.route('/')
def index():
    return render_template('cleanup.html')


@cleanup_bp.route('/api/user-temp', methods=['POST'])
def api_clean_user_temp():
    result = cleanup_svc.clean_user_temp()
    get_log().add_entry('cleanup', 'Clean user temp', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/windows-temp', methods=['POST'])
def api_clean_windows_temp():
    result = cleanup_svc.clean_windows_temp()
    get_log().add_entry('cleanup', 'Clean Windows temp', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/software-distribution', methods=['POST'])
def api_clean_software_dist():
    result = cleanup_svc.clean_software_distribution()
    get_log().add_entry('cleanup', 'Clean SoftwareDistribution', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/inet-cache', methods=['POST'])
def api_clean_inet_cache():
    result = cleanup_svc.clean_inet_cache()
    get_log().add_entry('cleanup', 'Clean INetCache', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/recycle-bin', methods=['POST'])
def api_empty_recycle_bin():
    result = cleanup_svc.empty_recycle_bin()
    get_log().add_entry('cleanup', 'Empty Recycle Bin', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/dns-cache', methods=['POST'])
def api_flush_dns():
    result = cleanup_svc.flush_dns_cache()
    get_log().add_entry('cleanup', 'Flush DNS cache', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/cleanmgr', methods=['POST'])
def api_cleanmgr():
    result = cleanup_svc.run_cleanmgr()
    get_log().add_entry('cleanup', 'Disk Cleanup (cleanmgr)', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/component-cleanup', methods=['POST'])
def api_component_cleanup():
    result = cleanup_svc.dism_component_cleanup()
    get_log().add_entry('cleanup', 'DISM ComponentCleanup', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/restart-explorer', methods=['POST'])
def api_restart_explorer():
    result = cleanup_svc.restart_explorer()
    get_log().add_entry('cleanup', 'Restart Explorer', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/retrim', methods=['POST'])
def api_retrim():
    result = cleanup_svc.retrim_ssd()
    get_log().add_entry('cleanup', 'ReTrim SSD', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/defrag', methods=['POST'])
def api_defrag():
    result = cleanup_svc.defrag_hdd()
    get_log().add_entry('cleanup', 'Defragment HDD', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/analyze-fragmentation')
def api_analyze_frag():
    result = cleanup_svc.analyze_fragmentation()
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/scan-duplicates', methods=['POST'])
def api_scan_duplicates():
    directory = request.json.get('directory') if request.is_json else None
    result = cleanup_svc.scan_duplicate_files(directory)
    get_log().add_entry('cleanup', 'Scan duplicate files', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/disable-sysmain', methods=['POST'])
def api_disable_sysmain():
    result = cleanup_svc.disable_sysmain()
    get_log().add_entry('cleanup', 'Disable SysMain', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/disable-wsearch', methods=['POST'])
def api_disable_wsearch():
    result = cleanup_svc.disable_windows_search()
    get_log().add_entry('cleanup', 'Disable Windows Search', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@cleanup_bp.route('/api/store-cache', methods=['POST'])
def api_store_cache():
    result = cleanup_svc.reset_windows_store_cache()
    get_log().add_entry('cleanup', 'Reset Store cache', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())
