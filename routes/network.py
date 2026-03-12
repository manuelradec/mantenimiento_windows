"""Network routes."""
from flask import Blueprint, render_template, jsonify, request

from services import network_tools as net_svc
from services.reports import get_log

network_bp = Blueprint('network', __name__)


@network_bp.route('/')
def index():
    return render_template('network.html')


@network_bp.route('/api/flush-dns', methods=['POST'])
def api_flush_dns():
    result = net_svc.flush_dns()
    get_log().add_entry('network', 'Flush DNS', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/release-ip', methods=['POST'])
def api_release_ip():
    result = net_svc.release_ip()
    get_log().add_entry('network', 'Release IP', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/renew-ip', methods=['POST'])
def api_renew_ip():
    result = net_svc.renew_ip()
    get_log().add_entry('network', 'Renew IP', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/reset-ip-stack', methods=['POST'])
def api_reset_ip_stack():
    result = net_svc.reset_ip_stack()
    get_log().add_entry('network', 'Reset IP stack', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/reset-winsock', methods=['POST'])
def api_reset_winsock():
    result = net_svc.reset_winsock()
    get_log().add_entry('network', 'Reset Winsock', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/tcp-global')
def api_tcp_global():
    return jsonify(net_svc.show_tcp_global().to_dict())


@network_bp.route('/api/set-autotuning', methods=['POST'])
def api_set_autotuning():
    result = net_svc.set_autotuning_normal()
    get_log().add_entry('network', 'Set autotuning normal', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/test-connectivity', methods=['POST'])
def api_test_connectivity():
    data = request.get_json(silent=True) or {}
    host = data.get('host', '8.8.8.8')
    port = data.get('port', 443)
    result = net_svc.test_connectivity(host, port)
    return jsonify(result.to_dict())


@network_bp.route('/api/adapters')
def api_adapters():
    return jsonify(net_svc.get_network_adapters().to_dict())


@network_bp.route('/api/ip-config')
def api_ip_config():
    return jsonify(net_svc.get_ip_configuration().to_dict())


@network_bp.route('/api/smb-sessions')
def api_smb_sessions():
    return jsonify(net_svc.show_smb_sessions().to_dict())


@network_bp.route('/api/clear-smb', methods=['POST'])
def api_clear_smb():
    result = net_svc.clear_smb_sessions()
    get_log().add_entry('network', 'Clear SMB sessions', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@network_bp.route('/api/proxy')
def api_proxy():
    return jsonify(net_svc.show_proxy_settings().to_dict())


@network_bp.route('/api/services')
def api_services():
    return jsonify(net_svc.show_network_services().to_dict())


@network_bp.route('/api/shared-folders')
def api_shared_folders():
    return jsonify(net_svc.get_shared_folders().to_dict())


@network_bp.route('/api/repair', methods=['POST'])
def api_network_repair():
    results = net_svc.run_network_repair()
    get_log().add_entry('network', 'Network repair sequence', 'success',
                        result='Repair sequence completed')
    return jsonify(results)
