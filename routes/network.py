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


@network_bp.route('/api/managed-adapters')
def api_managed_adapters():
    """Return adapters with manageability metadata for the adapter management UI."""
    return jsonify(net_svc.get_manageable_adapters())


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


@network_bp.route('/api/purge-netbios', methods=['POST'])
def api_purge_netbios():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'network.purge_netbios', net_svc.purge_netbios_cache,
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


@network_bp.route('/api/targets')
def api_targets():
    """Return the RADEC predefined connectivity target catalog."""
    return jsonify(net_svc.get_radec_targets())


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


@network_bp.route('/api/test-catalog', methods=['POST'])
def api_test_catalog():
    """
    Run a connectivity test for a RADEC catalog target.
    Body: { host, label, port (optional, null for ICMP) }
    """
    data = request.get_json(silent=True) or {}
    host = str(data.get('host', '')).strip()
    port = data.get('port')  # None or int
    label = str(data.get('label', host)).strip()

    # Normalize port: empty string / null / 0 → None (ICMP test)
    if port is not None:
        try:
            port = int(port)
            if port <= 0:
                port = None
        except (ValueError, TypeError):
            port = None

    def handler():
        return net_svc.test_connectivity(host, port)

    result = execute_governed_action(
        'network.test_connectivity', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    # Attach label to result so the frontend can use it in the toast/output
    if isinstance(result, dict):
        result['_label'] = label
        result['_host'] = host
        result['_port'] = port
    return jsonify(result)


@network_bp.route('/api/managed-services')
def api_managed_services():
    """Return current status and startup type of the 7 managed network services."""
    return jsonify(net_svc.get_managed_services())


@network_bp.route('/api/set-service-startup', methods=['POST'])
def api_set_service_startup():
    """Change startup type (Manual/Automatic) of a managed network service."""
    data = request.get_json(silent=True) or {}
    service_name = str(data.get('service_name', '')).strip()
    startup_type = str(data.get('startup_type', '')).strip()

    def handler():
        return net_svc.set_service_startup(service_name, startup_type)

    result = execute_governed_action(
        'network.service_startup', handler,
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


@network_bp.route('/api/enable-adapter', methods=['POST'])
def api_enable_adapter():
    data = request.get_json(silent=True) or {}
    adapter_name = str(data.get('adapter_name', '')).strip()

    def handler():
        return net_svc.enable_adapter(adapter_name)

    result = execute_governed_action(
        'network.enable_adapter', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@network_bp.route('/api/disable-adapter', methods=['POST'])
def api_disable_adapter():
    data = request.get_json(silent=True) or {}
    adapter_name = str(data.get('adapter_name', '')).strip()

    def handler():
        return net_svc.disable_adapter(adapter_name)

    result = execute_governed_action(
        'network.disable_adapter', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
