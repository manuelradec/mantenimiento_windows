"""
Startup Application Management routes.

All mutating endpoints (enable/disable) go through execute_governed_action().
The read-only /api/items endpoint bypasses governance (diagnostic only).
"""
import logging

from flask import Blueprint, render_template, jsonify, request

from services import startup_tools as startup_svc
from core.governance import execute_governed_action

startup_bp = Blueprint('startup', __name__)
logger = logging.getLogger('cleancpu.startup_routes')


@startup_bp.route('/')
def index():
    return render_template('startup.html')


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------

@startup_bp.route('/api/items')
def api_items():
    """Return all startup items with manageable flags.  No admin required."""
    result = startup_svc.get_startup_items()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Mutating — governed
# ---------------------------------------------------------------------------

@startup_bp.route('/api/disable', methods=['POST'])
def api_disable():
    """Disable a startup item (registry or Startup folder)."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    location = str(data.get('location', '')).strip()

    if not name or not location:
        return jsonify({'status': 'error', 'error': 'name y location son obligatorios.'}), 400

    def handler():
        return startup_svc.set_startup_item(name, location, enabled=False)

    result = execute_governed_action(
        'startup.disable_item',
        handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@startup_bp.route('/api/enable', methods=['POST'])
def api_enable():
    """Re-enable a previously disabled startup item."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    location = str(data.get('location', '')).strip()

    if not name or not location:
        return jsonify({'status': 'error', 'error': 'name y location son obligatorios.'}), 400

    def handler():
        return startup_svc.set_startup_item(name, location, enabled=True)

    result = execute_governed_action(
        'startup.enable_item',
        handler,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
