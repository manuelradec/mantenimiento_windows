"""Sharing and NetBIOS routes — ALL mutating endpoints governed."""
from flask import Blueprint, render_template, jsonify, request

from services import sharing_tools as sharing_svc
from core.governance import execute_governed_action

sharing_bp = Blueprint('sharing', __name__)


@sharing_bp.route('/')
def index():
    return render_template('sharing.html')


# --- Read-only ---

@sharing_bp.route('/api/settings')
def api_settings():
    """Return sharing settings overview (network discovery, file sharing, SMB, public folder)."""
    return jsonify(sharing_svc.get_sharing_settings())


@sharing_bp.route('/api/netbios-adapters')
def api_netbios_adapters():
    """Return IP-enabled adapters with their NetBIOS mode."""
    return jsonify(sharing_svc.get_netbios_adapters())


# --- Mutating endpoints — ALL governed ---

@sharing_bp.route('/api/enable-network-discovery', methods=['POST'])
def api_enable_network_discovery():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'sharing.enable_network_discovery',
        sharing_svc.enable_network_discovery,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@sharing_bp.route('/api/disable-network-discovery', methods=['POST'])
def api_disable_network_discovery():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'sharing.disable_network_discovery',
        sharing_svc.disable_network_discovery,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@sharing_bp.route('/api/set-netbios', methods=['POST'])
def api_set_netbios():
    data = request.get_json(silent=True) or {}
    adapter_index = data.get('adapter_index')
    mode = data.get('mode')

    def handler():
        return sharing_svc.set_netbios_mode(adapter_index, mode)

    result = execute_governed_action(
        'sharing.set_netbios', handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
