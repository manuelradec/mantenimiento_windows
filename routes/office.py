"""
Office License routes.
Provides inspection and official activation of Microsoft Office.
"""
import logging
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, session

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
        # Persist to session for page auto-load and Phase 3B report generation.
        # Stored: status, human message, parsed fields (partial_key = last-5 chars, safe).
        # Not stored: raw_output (too large), full keys (never available).
        # Guard: skip for not_applicable (non-Windows stub — no useful data to cache).
        if result.get('status') != 'not_applicable':
            session['office_license_last'] = {
                'status': result.get('status'),
                'message': result.get('message', ''),
                'parsed': result.get('parsed', {}),
                'inspected_at': datetime.now().isoformat(),
            }
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


# ---------------------------------------------------------------------------
# Phase 4 — New routes
# ---------------------------------------------------------------------------

@office_bp.route('/api/license_cache')
def api_license_cache():
    """
    Return the cached license status stored by the last /api/inspect call.
    Used by the Office page on load to pre-populate the inspect panel
    without re-running ospp.vbs on every visit.
    Returns {status:'ok', cached:{...}} or {status:'no_cache'}.
    """
    cached = session.get('office_license_last')
    if cached:
        return jsonify({'status': 'ok', 'cached': cached})
    return jsonify({'status': 'no_cache'})


@office_bp.route('/api/paqueteria')
def api_paqueteria():
    """List installed programs from the Windows registry (Paquetería section)."""
    from services.office_tools import get_installed_packages
    try:
        result = get_installed_packages()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Paqueteria error: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'packages': []}), 500


@office_bp.route('/api/repair', methods=['POST'])
def api_repair():
    """
    Trigger Office ClickToRun repair.
    Body: {"type": "quick" | "online"}
    C2R only — returns not_found if OfficeClickToRun.exe is absent.
    """
    data = request.get_json(silent=True) or {}
    repair_type = data.get('type', 'quick')
    if repair_type not in ('quick', 'online'):
        return jsonify({'status': 'error', 'message': 'Tipo de reparacion no valido.'}), 400
    from services.office_tools import repair_office
    try:
        result = repair_office(repair_type)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Office repair error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@office_bp.route('/api/safe_mode', methods=['POST'])
def api_safe_mode():
    """Launch Outlook in safe mode (/safe). Returns immediately after launch."""
    from services.office_tools import launch_office_safe_mode
    try:
        result = launch_office_safe_mode()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Outlook safe mode error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@office_bp.route('/api/configure_mail', methods=['POST'])
def api_configure_mail():
    """Open the Windows Mail / Outlook profile manager (mlcfg32.cpl)."""
    from services.office_tools import configure_mail_profile
    try:
        result = configure_mail_profile()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Mail configure error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@office_bp.route('/api/scanpst', methods=['POST'])
def api_scanpst():
    """Launch SCANPST.EXE — Outlook Inbox Repair Tool."""
    from services.office_tools import launch_scanpst
    try:
        result = launch_scanpst()
        return jsonify(result)
    except Exception as e:
        logger.error(f"scanpst error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@office_bp.route('/api/rebuild_index', methods=['POST'])
def api_rebuild_index():
    """
    Rebuild Windows Search index (used by Outlook for full-text search).
    Stops WSearch, clears the catalog directory, restarts WSearch.
    Requires admin.
    """
    from services.office_tools import rebuild_outlook_search_index
    try:
        result = rebuild_outlook_search_index()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Rebuild index error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
