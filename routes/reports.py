"""Reports and logging routes."""
from flask import Blueprint, render_template, jsonify, send_file

from services.reports import get_log

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
def index():
    log = get_log()
    return render_template('reports.html',
                           entries=log.entries,
                           summary=log.get_summary())


@reports_bp.route('/api/entries')
def api_entries():
    log = get_log()
    return jsonify({
        'entries': log.entries,
        'summary': log.get_summary(),
    })


@reports_bp.route('/api/export/json', methods=['POST'])
def api_export_json():
    log = get_log()
    filepath = log.export_json()
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/export/txt', methods=['POST'])
def api_export_txt():
    log = get_log()
    filepath = log.export_txt()
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/export/html', methods=['POST'])
def api_export_html():
    log = get_log()
    filepath = log.export_html()
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/download/<format>')
def api_download(format):
    log = get_log()
    if format == 'json':
        filepath = log.export_json()
    elif format == 'txt':
        filepath = log.export_txt()
    elif format == 'html':
        filepath = log.export_html()
    else:
        return jsonify({'error': 'Invalid format'}), 400

    return send_file(filepath, as_attachment=True)
