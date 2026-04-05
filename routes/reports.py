"""Reports and logging routes - SQLite-first reporting with incident-grade bundles."""
import json
import os
from datetime import datetime
from html import escape as html_escape

from flask import Blueprint, render_template, jsonify, send_file, current_app

from core.persistence import AuditStore, JobStore, SessionStore, SnapshotStore, EventViewerStore
from config import Config

reports_bp = Blueprint('reports', __name__)

_MAINT_TYPE_LABELS = {
    'preventivo': 'MANTENIMIENTO PREVENTIVO',
    'correctivo': 'MANTENIMIENTO CORRECTIVO',
    'revision': 'REVISIÓN',
}


def _maint_type_label(maint_type):
    return _MAINT_TYPE_LABELS.get((maint_type or 'preventivo').lower(),
                                  'MANTENIMIENTO PREVENTIVO')


@reports_bp.route('/')
def index():
    session_id = current_app.config.get('SESSION_ID', 'unknown')
    summary = AuditStore.get_summary(session_id)
    entries = AuditStore.get_all(session_id, limit=200)
    return render_template('reports.html', entries=entries, summary=summary)


@reports_bp.route('/api/entries')
def api_entries():
    session_id = current_app.config.get('SESSION_ID', 'unknown')
    entries = AuditStore.get_all(session_id, limit=200)
    summary = AuditStore.get_summary(session_id)
    return jsonify({'entries': entries, 'summary': summary})


@reports_bp.route('/api/export/json', methods=['POST'])
def api_export_json():
    bundle = _build_incident_bundle()
    filepath = os.path.join(Config.REPORT_DIR,
                            f'incident_{bundle["session_id"]}.json')
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2, default=str)
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/export/txt', methods=['POST'])
def api_export_txt():
    bundle = _build_incident_bundle()
    filepath = os.path.join(Config.REPORT_DIR,
                            f'incident_{bundle["session_id"]}.txt')
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(_render_text_report(bundle))
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/export/html', methods=['POST'])
def api_export_html():
    bundle = _build_incident_bundle()
    filepath = os.path.join(Config.REPORT_DIR,
                            f'incident_{bundle["session_id"]}.html')
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(_render_html_report(bundle))
    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/download/<format>')
def api_download(format):
    bundle = _build_incident_bundle()
    session_id = bundle['session_id']

    if format == 'json':
        filepath = os.path.join(Config.REPORT_DIR, f'incident_{session_id}.json')
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2, default=str)
    elif format == 'txt':
        filepath = os.path.join(Config.REPORT_DIR, f'incident_{session_id}.txt')
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(_render_text_report(bundle))
    elif format == 'html':
        filepath = os.path.join(Config.REPORT_DIR, f'incident_{session_id}.html')
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(_render_html_report(bundle))
    else:
        return jsonify({'error': 'Invalid format'}), 400

    return send_file(filepath, as_attachment=True)


def _build_incident_bundle() -> dict:
    """Build a comprehensive incident-grade report bundle from SQLite."""
    session_id = current_app.config.get('SESSION_ID', 'unknown')
    hostname = current_app.config.get('HOSTNAME', 'unknown')
    username = current_app.config.get('USERNAME', 'unknown')

    session_info = SessionStore.get(session_id) or {}
    summary = AuditStore.get_summary(session_id)
    audit_entries = AuditStore.get_all(session_id, limit=500)
    jobs = JobStore.list_by_session(session_id, limit=200)
    snapshots = SnapshotStore.get_by_session(session_id)
    events = EventViewerStore.get_by_session(session_id, limit=100)

    # System info
    from services.system_info import get_system_overview
    from services.permissions import get_elevation_info
    sys_info = get_system_overview()
    elevation = get_elevation_info()

    # Compute reboot_required
    reboot_required = any(j.get('needs_reboot') for j in jobs)

    # Compute warnings and errors
    warnings = [e for e in audit_entries if e.get('status') in ('warning', 'partial_success')]
    errors = [e for e in audit_entries if e.get('status') in ('failed', 'error')]

    return {
        'report_type': 'incident_bundle',
        'generated_at': datetime.now().isoformat(),
        'app_version': Config.APP_VERSION,
        'session_id': session_id,
        'hostname': hostname,
        'username': username,
        'is_admin': elevation['is_admin'],
        'os_info': {
            'os_name': sys_info.get('os_name', ''),
            'os_version': sys_info.get('os_version', ''),
            'os_release': sys_info.get('os_release', ''),
            'architecture': sys_info.get('architecture', ''),
        },
        'session_info': session_info,
        'executive_summary': {
            'total_actions': summary.get('total_actions', 0),
            'by_status': summary.get('by_status', {}),
            'by_module': summary.get('by_module', {}),
            'reboot_required': reboot_required,
            'warning_count': len(warnings),
            'error_count': len(errors),
        },
        'audit_entries': audit_entries,
        'jobs': jobs,
        'snapshots': snapshots,
        'event_viewer': events,
        'recommendations': _generate_recommendations(audit_entries, jobs, reboot_required),
    }


@reports_bp.route('/api/export/fo-ti-19', methods=['POST'])
def api_export_fo_ti_19():
    """Export FO-TI-19 Hoja de Servicio HTML report for current equipment."""
    from flask import request
    from services.maintenance_report import generate_fo_ti_19_html

    data = request.get_json(silent=True) or {}
    sucursal = data.get('sucursal', '')
    technician_name = data.get('technician_name', '')
    maint_type = data.get('maint_type', 'preventivo')
    model_override = data.get('model', '')
    tech_address = data.get('tech_address', '')
    tech_phone = data.get('tech_phone', '')
    tech_email = data.get('tech_email', '')
    operator_name = data.get('operator_name', '')
    op_address = data.get('op_address', '')
    op_phone = data.get('op_phone', '')
    op_email = data.get('op_email', '')
    accessories = data.get('accessories', '')
    drive_overrides = data.get('drive_overrides') or {}

    # Collect system info
    from routes.maintenance import _collect_system_info
    system_info = _collect_system_info()

    # Build steps from audit log
    session_id = current_app.config.get('SESSION_ID', 'unknown')
    audit_entries = AuditStore.get_all(session_id, limit=200)
    steps = []
    for entry in audit_entries:
        steps.append({
            'name': entry.get('action', ''),
            'status': 'completed' if entry.get('status') == 'success' else entry.get('status', ''),
            'elapsed': (entry.get('duration_ms', 0) or 0) / 1000.0,
            'message': entry.get('stdout_preview', '') or entry.get('stderr_preview', '') or '',
        })

    html = generate_fo_ti_19_html(
        system_info, steps, {},
        sucursal=sucursal,
        technician_name=technician_name,
        maint_type=maint_type,
        model_override=model_override,
        tech_address=tech_address,
        tech_phone=tech_phone,
        tech_email=tech_email,
        operator_name=operator_name,
        op_address=op_address,
        op_phone=op_phone,
        op_email=op_email,
        accessories_override=accessories,
        drive_overrides=drive_overrides,
    )

    filename = f'FO-TI-19_{system_info.get("hostname", "EQUIPO")}_{datetime.now().strftime("%Y-%m-%d")}.html'
    filepath = os.path.join(Config.REPORT_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/download/fo-ti-19')
def api_download_fo_ti_19():
    """Download FO-TI-19 HTML report."""
    from flask import request
    from services.maintenance_report import generate_fo_ti_19_html

    sucursal = request.args.get('sucursal', '')
    technician_name = request.args.get('technician_name', '')
    maint_type = request.args.get('maint_type', 'preventivo')
    model_override = request.args.get('model', '')
    tech_address = request.args.get('tech_address', '')
    tech_phone = request.args.get('tech_phone', '')
    tech_email = request.args.get('tech_email', '')
    operator_name = request.args.get('operator_name', '')
    op_address = request.args.get('op_address', '')
    op_phone = request.args.get('op_phone', '')
    op_email = request.args.get('op_email', '')
    accessories = request.args.get('accessories', '')
    # drive_overrides not carried in GET; omit (POST export is the primary form path)

    from routes.maintenance import _collect_system_info
    system_info = _collect_system_info()

    session_id = current_app.config.get('SESSION_ID', 'unknown')
    audit_entries = AuditStore.get_all(session_id, limit=200)
    steps = []
    for entry in audit_entries:
        steps.append({
            'name': entry.get('action', ''),
            'status': 'completed' if entry.get('status') == 'success' else entry.get('status', ''),
            'elapsed': (entry.get('duration_ms', 0) or 0) / 1000.0,
            'message': entry.get('stdout_preview', '') or '',
        })

    html = generate_fo_ti_19_html(
        system_info, steps, {},
        sucursal=sucursal,
        technician_name=technician_name,
        maint_type=maint_type,
        model_override=model_override,
        tech_address=tech_address,
        tech_phone=tech_phone,
        tech_email=tech_email,
        operator_name=operator_name,
        op_address=op_address,
        op_phone=op_phone,
        op_email=op_email,
        accessories_override=accessories,
        drive_overrides={},
    )

    filename = f'FO-TI-19_{system_info.get("hostname", "EQUIPO")}_{datetime.now().strftime("%Y-%m-%d")}.html'
    filepath = os.path.join(Config.REPORT_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    return send_file(filepath, as_attachment=True)


@reports_bp.route('/api/export/fo-ti-20', methods=['POST'])
def api_export_fo_ti_20():
    """Export FO-TI-20 Bitacora de mantenimiento HTML report."""
    from flask import request
    from services.maintenance_report import generate_fo_ti_20_html

    data = request.get_json(silent=True) or {}
    sucursal = data.get('sucursal', '')
    entries = data.get('entries', [])
    maint_type = data.get('maint_type', 'preventivo')

    # If no entries provided, build from current session audit log
    if not entries:
        from routes.maintenance import _collect_system_info
        system_info = _collect_system_info()
        username = current_app.config.get('USERNAME', 'unknown')

        entries = [{
            'fecha': datetime.now().strftime('%d/%m/%Y'),
            'usuario': username,
            'equipo': system_info.get('model', 'N/A'),
            'reporte_final': _maint_type_label(maint_type),
        }]

    html = generate_fo_ti_20_html(entries, sucursal=sucursal)

    filename = f'FO-TI-20_{sucursal or "SUCURSAL"}_{datetime.now().strftime("%Y-%m-%d")}.html'
    filepath = os.path.join(Config.REPORT_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    return jsonify({'status': 'success', 'path': filepath})


@reports_bp.route('/api/download/fo-ti-20')
def api_download_fo_ti_20():
    """Download FO-TI-20 Bitacora HTML report."""
    from flask import request
    from services.maintenance_report import generate_fo_ti_20_html

    sucursal = request.args.get('sucursal', '')
    maint_type = request.args.get('maint_type', 'preventivo')

    from routes.maintenance import _collect_system_info
    system_info = _collect_system_info()
    username = current_app.config.get('USERNAME', 'unknown')

    entries = [{
        'fecha': datetime.now().strftime('%d/%m/%Y'),
        'usuario': username,
        'equipo': system_info.get('model', 'N/A'),
        'reporte_final': _maint_type_label(maint_type),
    }]

    html = generate_fo_ti_20_html(entries, sucursal=sucursal)

    filename = f'FO-TI-20_{sucursal or "SUCURSAL"}_{datetime.now().strftime("%Y-%m-%d")}.html'
    filepath = os.path.join(Config.REPORT_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    return send_file(filepath, as_attachment=True)


@reports_bp.route('/api/hardware-upgrades')
def api_hardware_upgrades():
    """Get hardware upgrade opportunities for current equipment."""
    from services.system_info import get_upgrade_opportunities
    try:
        opportunities = get_upgrade_opportunities()
        return jsonify({'status': 'success', 'data': opportunities})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


def _generate_recommendations(entries, jobs, reboot_required) -> list[str]:
    """Auto-generate recommendations based on session data."""
    recs = []
    if reboot_required:
        recs.append('REBOOT REQUIRED: One or more actions require a system restart to complete.')

    error_count = sum(1 for e in entries if e.get('status') in ('failed', 'error'))
    if error_count > 0:
        recs.append(f'{error_count} action(s) failed. Review errors and retry or escalate.')

    partial = sum(1 for e in entries if e.get('status') == 'partial_success')
    if partial > 0:
        recs.append(f'{partial} action(s) partially succeeded. Review individual step results.')

    if not entries:
        recs.append('No actions were performed in this session.')

    return recs


def _render_text_report(bundle: dict) -> str:
    """Render the incident bundle as a human-readable text report."""
    lines = [
        '=' * 70,
        f'  INCIDENT REPORT - {Config.APP_NAME} v{Config.APP_VERSION}',
        f'  Session: {bundle["session_id"]}',
        f'  Generated: {bundle["generated_at"]}',
        f'  Host: {bundle["hostname"]} | User: {bundle["username"]} | Admin: {bundle["is_admin"]}',
        f'  OS: {bundle["os_info"].get("os_name", "")} {bundle["os_info"].get("os_version", "")}',
        '=' * 70,
        '',
        'EXECUTIVE SUMMARY',
        '-' * 40,
        f'  Total actions: {bundle["executive_summary"]["total_actions"]}',
        f'  Reboot required: {bundle["executive_summary"]["reboot_required"]}',
        f'  Warnings: {bundle["executive_summary"]["warning_count"]}',
        f'  Errors: {bundle["executive_summary"]["error_count"]}',
    ]

    for status, count in bundle['executive_summary'].get('by_status', {}).items():
        lines.append(f'    {status}: {count}')

    lines.append('')
    lines.append('RECOMMENDATIONS')
    lines.append('-' * 40)
    for rec in bundle.get('recommendations', []):
        lines.append(f'  * {rec}')

    lines.append('')
    lines.append('DETAILED AUDIT LOG')
    lines.append('=' * 70)
    for entry in bundle.get('audit_entries', []):
        lines.append(f'  [{entry.get("timestamp", "")}] [{entry.get("module", "")}] '
                     f'{entry.get("action", "")} -> {entry.get("status", "")}')
        if entry.get('stdout_preview'):
            lines.append(f'    Output: {entry["stdout_preview"][:200]}')
        if entry.get('stderr_preview'):
            lines.append(f'    Error: {entry["stderr_preview"][:200]}')
        if entry.get('duration_ms'):
            lines.append(f'    Duration: {entry["duration_ms"]}ms')

    lines.append('')
    lines.append('=' * 70)
    lines.append('END OF REPORT')

    return '\n'.join(lines)


def _render_html_report(bundle: dict) -> str:
    """Render the incident bundle as an HTML report with proper escaping."""
    he = html_escape

    rows = ''
    for entry in bundle.get('audit_entries', []):
        status = entry.get('status', '')
        status_class = {
            'completed': 'color:#22543d;font-weight:bold',
            'success': 'color:#22543d;font-weight:bold',
            'warning': 'color:#744210;font-weight:bold',
            'partial_success': 'color:#744210;font-weight:bold',
            'failed': 'color:#9b2c2c;font-weight:bold',
            'error': 'color:#9b2c2c;font-weight:bold',
        }.get(status, '')
        detail = (entry.get('stdout_preview') or entry.get('stderr_preview') or '-')[:150]
        dur = f'{entry.get("duration_ms", 0)}ms' if entry.get('duration_ms') else '-'
        rows += (
            f'<tr>'
            f'<td>{he(str(entry.get("timestamp", ""))[:19])}</td>'
            f'<td>{he(str(entry.get("module", "")))}</td>'
            f'<td>{he(str(entry.get("action", "")))}</td>'
            f'<td style="{status_class}">{he(str(status))}</td>'
            f'<td>{he(str(entry.get("risk_class", "")))}</td>'
            f'<td>{he(str(dur))}</td>'
            f'<td>{he(str(detail))}</td>'
            f'</tr>\n'
        )

    recs_html = ''.join(f'<li>{he(r)}</li>' for r in bundle.get('recommendations', []))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CleanCPU Incident Report - {he(bundle["session_id"])}</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a365d; }} h2 {{ color: #2d3748; margin-top: 24px; }}
        table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 12px; }}
        th {{ background: #2d3748; color: white; }}
        .card {{ background: white; padding: 16px; border-radius: 6px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        ul {{ margin: 8px 0; }}
    </style>
</head>
<body>
    <h1>CleanCPU Incident Report</h1>
    <div class="card">
        <div class="grid">
            <div><strong>Session:</strong> {he(bundle["session_id"])}</div>
            <div><strong>Generated:</strong> {he(bundle["generated_at"][:19])}</div>
            <div><strong>Hostname:</strong> {he(bundle["hostname"])}</div>
            <div><strong>Username:</strong> {he(bundle["username"])}</div>
            <div><strong>Admin:</strong> {he(str(bundle["is_admin"]))}</div>
            <div><strong>Version:</strong> {he(Config.APP_VERSION)}</div>
            <div><strong>OS:</strong> {he(bundle["os_info"].get("os_name", ""))} {he(bundle["os_info"].get("os_version", ""))}</div>
            <div><strong>Reboot Required:</strong> {he(str(bundle["executive_summary"]["reboot_required"]))}</div>
        </div>
    </div>
    <h2>Executive Summary</h2>
    <div class="card">
        <p><strong>Total Actions:</strong> {bundle["executive_summary"]["total_actions"]} |
           <strong>Warnings:</strong> {bundle["executive_summary"]["warning_count"]} |
           <strong>Errors:</strong> {bundle["executive_summary"]["error_count"]}</p>
    </div>
    <h2>Recommendations</h2>
    <div class="card"><ul>{recs_html}</ul></div>
    <h2>Audit Log</h2>
    <table>
        <thead><tr><th>Time</th><th>Module</th><th>Action</th><th>Status</th><th>Risk</th><th>Duration</th><th>Details</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <footer style="margin-top:20px;font-size:11px;color:#a0aec0;">
        Generated by CleanCPU v{he(Config.APP_VERSION)}
    </footer>
</body>
</html>'''
