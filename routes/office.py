"""
Office License routes.
Provides inspection and official activation of Microsoft Office.
"""
import logging

from flask import Blueprint, render_template, jsonify, request

office_bp = Blueprint('office', __name__)
logger = logging.getLogger('cleancpu.office_routes')


@office_bp.route('/')
def index():
    return render_template('office.html')


@office_bp.route('/api/info')
def api_info():
    """Return registry-based Office installation info (no admin required)."""
    from services.office_tools import get_installation_info
    try:
        info = get_installation_info()
        return jsonify(info)
    except Exception as e:
        logger.error(f"Office info error: {e}")
        return jsonify({'error': str(e)}), 500


@office_bp.route('/api/inspect', methods=['POST'])
def api_inspect():
    """Run ospp.vbs /dstatus to get full license status. Requires admin."""
    from services.office_tools import inspect_license
    try:
        result = inspect_license()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Office inspect error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@office_bp.route('/api/activate', methods=['POST'])
def api_activate():
    """
    Install a product key and trigger Office activation via ospp.vbs.
    The key is accepted in the JSON body and NEVER echoed back in full.
    Only the masked form is returned.
    """
    data = request.get_json(silent=True) or {}
    key = (data.get('key') or '').strip()

    if not key:
        return jsonify({
            'status': 'invalid_key',
            'message': 'No se recibio ninguna clave de producto.',
            'masked_key': '',
        }), 400

    from services.office_tools import activate_with_key
    try:
        result = activate_with_key(key)
        # Ensure the full key is never in the response
        result.pop('key', None)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Office activation error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error inesperado: {str(e)}',
            'masked_key': '(no disponible)',
        }), 500
