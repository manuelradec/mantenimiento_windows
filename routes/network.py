"""Network routes - ALL mutating endpoints governed via execute_governed_action."""
from flask import Blueprint, render_template, jsonify, request

from services import network_tools as net_svc
from core.governance import execute_governed_action

network_bp = Blueprint('network', __name__)


@network_bp.route('/')
def index():
    return render_template('network.html')


# --- Read-only diagnostics ---

@network_bp.route('/api/tcp-global')
def api_tcp_global():
    return jsonify(net_svc.show_tcp_global().to_dict())


@network_bp.route('/api/adapters')
def api_adapters():
    return jsonify(net_svc.get_network_adapters().to_dict())


@network_bp.route('/api/ip-config')
def api_ip_config():
    return jsonify(net_svc.get_ip_configuration().to_dict())


@network_bp.route('/api/smb-sessions')
def api_smb_sessions():
    return jsonify(net_svc.show_smb_sessions().to_dict())


@network_bp.route('/api/proxy')
def api_proxy():
    return jsonify(net_svc.show_proxy_settings().to_dict())


@network_bp.route('/api/services')
def api_services():
    return jsonify(net_svc.show_network_services().to_dict())


@network_bp.route('/api/shared-folders')
def api_shared_folders():
    return jsonify(net_svc.get_shared_folders().to_dict())


# --- Mutating endpoints - ALL governed ---

@network_bp.route('/api/flush-dns', methods=['POST'])
def api_flush_dns():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.flush_dns', net_svc.flush_dns,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/release-ip', methods=['POST'])
def api_release_ip():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.release_ip', net_svc.release_ip,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/renew-ip', methods=['POST'])
def api_renew_ip():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.renew_ip', net_svc.renew_ip,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/reset-ip-stack', methods=['POST'])
def api_reset_ip_stack():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.reset_ip_stack', net_svc.reset_ip_stack,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/reset-winsock', methods=['POST'])
def api_reset_winsock():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.reset_winsock', net_svc.reset_winsock,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/set-autotuning', methods=['POST'])
def api_set_autotuning():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.set_autotuning', net_svc.set_autotuning_normal,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/test-connectivity', methods=['POST'])
def api_test_connectivity():
    data = request.get_json(silent=True) or {}
    host = data.get('host', '8.8.8.8')
    port = data.get('port', 443)

    def handler():
        return net_svc.test_connectivity(host, port)

    result = execute_governed_action(
        'network.test_connectivity', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/clear-smb', methods=['POST'])
def api_clear_smb():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.clear_smb', net_svc.clear_smb_sessions,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/repair', methods=['POST'])
def api_network_repair():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.repair', net_svc.run_network_repair,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
