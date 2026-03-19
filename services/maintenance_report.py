"""
Maintenance Report Generation and Distribution.

Handles:
- HTML report generation
- Google Sheets integration (via gspread)
- Network share file copy
- RADEC Excel form FO-TI-19 generation (via openpyxl)
"""
import os
import sys
import shutil
import logging
from datetime import datetime

from config import Config

logger = logging.getLogger('cleancpu.maintenance_report')

# Target paths
GOOGLE_SHEET_ID = '1i1v67mXuVA5Aqo2slYkrhLi_fDeUb95q'
NETWORK_SHARE_BASE = r'\\192.168.122.215\soporte CLJ\Mantenimiento Anual'
CREDENTIALS_PATH = os.path.join(Config.BASE_PATH, 'credentials', 'service_account.json')


def generate_html_report(system_info, steps, session_data):
    """Generate an HTML maintenance report."""
    hostname = system_info.get('hostname', 'UNKNOWN')
    serial = system_info.get('serial', 'UNKNOWN')
    date_str = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    completed = sum(1 for s in steps if s.get('status') == 'completed')
    skipped = sum(1 for s in steps if s.get('status') == 'skipped')
    failed = sum(1 for s in steps if s.get('status') == 'failed')
    total_time = sum(s.get('elapsed', 0) for s in steps)
    status_text = 'COMPLETADO' if failed == 0 else 'PARCIAL'

    steps_html = ''
    for i, step in enumerate(steps, 1):
        status_color = {
            'completed': '#0AAE6B',
            'skipped': '#D6814A',
            'failed': '#E33B14',
            'cancelled': '#888',
        }.get(step.get('status', ''), '#666')
        steps_html += f'''
        <tr>
            <td style="padding:6px 10px;">{i}</td>
            <td style="padding:6px 10px;">{step.get('name', '')}</td>
            <td style="padding:6px 10px;color:{status_color};font-weight:bold;">{step.get('status', 'N/A').upper()}</td>
            <td style="padding:6px 10px;">{step.get('elapsed', 0):.1f}s</td>
            <td style="padding:6px 10px;font-size:12px;">{step.get('message', '')}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Mantenimiento - {hostname} - {date_str}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 30px; color: #333; }}
        h1 {{ color: #274C9B; border-bottom: 3px solid #0AAE6B; padding-bottom: 8px; }}
        h2 {{ color: #0E7C5A; margin-top: 24px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
        th {{ background: #274C9B; color: #fff; padding: 8px 10px; text-align: left; }}
        td {{ border-bottom: 1px solid #ddd; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; }}
        .info-grid dt {{ font-weight: bold; color: #555; }}
        .info-grid dd {{ margin: 0; }}
        .status {{ font-size: 18px; font-weight: bold; color: {'#0AAE6B' if failed == 0 else '#E33B14'}; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #999; border-top: 1px solid #ddd; padding-top: 10px; }}
    </style>
</head>
<body>
    <h1>Reporte de Mantenimiento Lógico — RADEC AUTOPARTES</h1>
    <p class="status">Estado: {status_text}</p>
    <p>Fecha: {timestamp}</p>

    <h2>Identificación del equipo</h2>
    <dl class="info-grid">
        <dt>Hostname:</dt><dd>{hostname}</dd>
        <dt>IP:</dt><dd>{system_info.get('ip_address', 'N/A')}</dd>
        <dt>No. Serie:</dt><dd>{serial}</dd>
        <dt>Marca:</dt><dd>{system_info.get('manufacturer', 'N/A')}</dd>
        <dt>Modelo:</dt><dd>{system_info.get('model', 'N/A')}</dd>
        <dt>Procesador:</dt><dd>{system_info.get('processor', 'N/A')}</dd>
        <dt>RAM:</dt><dd>{system_info.get('ram_gb', 'N/A')}</dd>
        <dt>Disco:</dt><dd>{system_info.get('hard_drive', 'N/A')}</dd>
        <dt>Sistema operativo:</dt><dd>{system_info.get('os_version', 'N/A')}</dd>
    </dl>

    <h2>Pasos del mantenimiento</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Paso</th><th>Estado</th><th>Tiempo</th><th>Detalle</th></tr>
        </thead>
        <tbody>{steps_html}</tbody>
    </table>

    <h2>Resumen</h2>
    <ul>
        <li>Completados: {completed}/{len(steps)}</li>
        <li>Omitidos: {skipped}</li>
        <li>Fallidos: {failed}</li>
        <li>Tiempo total: {total_time:.0f} segundos</li>
    </ul>

    <div class="footer">
        Generado por CleanCPU v{Config.APP_VERSION} — RADEC AUTOPARTES<br>
        {timestamp}
    </div>
</body>
</html>'''

    return html


def save_report_locally(html_content, system_info):
    """Save the HTML report to the local reports directory."""
    hostname = system_info.get('hostname', 'UNKNOWN')
    serial = system_info.get('serial', 'UNKNOWN')
    date_str = datetime.now().strftime('%Y-%m-%d')

    filename = f'Mantenimiento_{hostname}_{serial}_{date_str}.html'
    local_path = os.path.join(Config.REPORT_DIR, filename)

    try:
        os.makedirs(Config.REPORT_DIR, exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Report saved locally: {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to save local report: {e}")
        return None


def save_to_network_share(html_content, system_info):
    """Save the report to the network share."""
    if sys.platform != 'win32':
        return {'status': 'skipped', 'reason': 'Only available on Windows'}

    hostname = system_info.get('hostname', 'UNKNOWN')
    serial = system_info.get('serial', 'UNKNOWN')
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f'Mantenimiento_{hostname}_{serial}_{date_str}.html'

    target_dir = os.path.join(NETWORK_SHARE_BASE, date_str)
    target_path = os.path.join(target_dir, filename)

    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Report saved to network share: {target_path}")
        return {'status': 'success', 'path': target_path}
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to save to network share: {e}")
        return {
            'status': 'error',
            'error': f'No se pudo guardar en la carpeta de red: {e}. '
                     'El reporte se guardó localmente.',
        }


def update_google_sheets(system_info, steps):
    """Append a row to the Google Sheets maintenance log."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.warning("gspread/google-auth not installed. Skipping Google Sheets update.")
        return {'status': 'skipped', 'reason': 'Bibliotecas de Google no instaladas.'}

    if not os.path.exists(CREDENTIALS_PATH):
        logger.warning(f"Google credentials not found at {CREDENTIALS_PATH}")
        return {
            'status': 'skipped',
            'reason': 'Credenciales de Google no configuradas. '
                      'Coloque el archivo service_account.json en la carpeta credentials/.',
        }

    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

        failed = sum(1 for s in steps if s.get('status') == 'failed')
        status_text = 'COMPLETADO' if failed == 0 else 'PARCIAL'

        details = '; '.join(
            f"{s.get('name', '')}: {s.get('status', '')}"
            for s in steps
        )

        row = [
            system_info.get('ip_address', 'N/A'),
            system_info.get('serial', 'N/A'),
            system_info.get('manufacturer', 'N/A'),
            system_info.get('model', 'N/A'),
            system_info.get('processor', 'N/A'),
            system_info.get('ram_gb', 'N/A'),
            system_info.get('hard_drive', 'N/A'),
            status_text,
            datetime.now().strftime('%d/%m/%Y'),
            details[:500],
        ]

        sheet.append_row(row, value_input_option='USER_ENTERED')
        logger.info("Google Sheets updated successfully")
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"Google Sheets update failed: {e}")
        return {'status': 'error', 'error': str(e)}


def generate_radec_excel(system_info, steps):
    """
    Generate the RADEC FO-TI-19 Excel form.
    If a template exists, use it; otherwise create from scratch.
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl not installed. Skipping Excel form generation.")
        return {'status': 'skipped', 'reason': 'openpyxl no está instalado.'}

    hostname = system_info.get('hostname', 'UNKNOWN')
    date_str = datetime.now().strftime('%Y-%m-%d')
    date_display = datetime.now().strftime('%d/%m/%Y')

    # Try to load template
    template_path = os.path.join(Config.BASE_PATH, 'templates_data', 'FO-TI-19_template.xlsx')
    if os.path.exists(template_path):
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'FO-TI-19'
        _build_form_from_scratch(ws, system_info, steps, date_display)

    # Fill common fields regardless of template presence
    _fill_form_fields(ws, system_info, steps, date_display)

    # Save
    filename = f'FO-TI-19_{hostname}_{date_str}.xlsx'
    local_path = os.path.join(Config.REPORT_DIR, filename)
    os.makedirs(Config.REPORT_DIR, exist_ok=True)

    try:
        wb.save(local_path)
        logger.info(f"RADEC Excel form saved: {local_path}")
    except Exception as e:
        logger.error(f"Failed to save Excel form: {e}")
        return {'status': 'error', 'error': str(e)}

    # Also copy to network share
    network_result = {'status': 'skipped'}
    if sys.platform == 'win32':
        try:
            net_dir = os.path.join(NETWORK_SHARE_BASE, date_str)
            os.makedirs(net_dir, exist_ok=True)
            net_path = os.path.join(net_dir, filename)
            shutil.copy2(local_path, net_path)
            network_result = {'status': 'success', 'path': net_path}
            logger.info(f"Excel form copied to network: {net_path}")
        except (PermissionError, OSError) as e:
            network_result = {'status': 'error', 'error': str(e)}
            logger.warning(f"Failed to copy Excel to network: {e}")

    return {
        'status': 'success',
        'local_path': local_path,
        'network': network_result,
    }


def _build_form_from_scratch(ws, system_info, steps, date_display):
    """Build FO-TI-19 form structure when no template exists."""
    from openpyxl.styles import Font, Alignment, PatternFill

    header_font = Font(bold=True, size=11)
    title_font = Font(bold=True, size=14, color='274C9B')
    fill_header = PatternFill(start_color='274C9B', end_color='274C9B', fill_type='solid')
    font_white = Font(bold=True, color='FFFFFF', size=10)

    # Title
    ws.merge_cells('A1:H1')
    ws['A1'] = 'HOJA DE SERVICIO MANTENIMIENTO DE EQUIPO DE CÓMPUTO'
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    # Header info
    ws['A2'] = 'Código:'
    ws['B2'] = 'FO-TI-19'
    ws['D2'] = 'Versión: 06/07'
    ws['F2'] = f'Fecha de Emisión: {date_display}'

    # Equipment section
    row = 4
    ws[f'A{row}'] = 'DATOS DEL EQUIPO'
    ws[f'A{row}'].font = header_font

    labels = [
        ('Hostname:', system_info.get('hostname', '')),
        ('Procesador:', system_info.get('processor', '')),
        ('RAM:', system_info.get('ram_gb', '')),
        ('Disco Duro:', system_info.get('hard_drive', '')),
        ('Sistema Operativo:', system_info.get('os_version', '')),
        ('No. Serie:', system_info.get('serial', '')),
        ('Marca:', system_info.get('manufacturer', '')),
        ('Modelo:', system_info.get('model', '')),
        ('IP:', system_info.get('ip_address', '')),
    ]
    for i, (label, value) in enumerate(labels):
        r = row + 1 + i
        ws[f'A{r}'] = label
        ws[f'A{r}'].font = Font(bold=True, size=10)
        ws[f'B{r}'] = str(value)

    # Service type
    row = 15
    ws[f'A{row}'] = 'TIPO DE SERVICIO'
    ws[f'A{row}'].font = header_font
    ws[f'A{row + 1}'] = 'Preventivo'
    ws[f'B{row + 1}'] = 'X'
    ws[f'B{row + 1}'].font = Font(bold=True, color='0AAE6B')

    # Activities
    row = 18
    ws[f'A{row}'] = 'ACTIVIDADES REALIZADAS'
    ws[f'A{row}'].font = header_font

    # Table header
    row += 1
    for col, header in enumerate(['#', 'Actividad', 'Estado', 'Tiempo', 'Detalle'], 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = font_white
        cell.fill = fill_header

    # Steps
    for i, step in enumerate(steps, 1):
        r = row + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=step.get('name', ''))
        ws.cell(row=r, column=3, value=(step.get('status', '')).upper())
        ws.cell(row=r, column=4, value=f"{step.get('elapsed', 0):.1f}s")
        ws.cell(row=r, column=5, value=step.get('message', ''))

    # Observations
    obs_row = row + len(steps) + 2
    ws[f'A{obs_row}'] = 'OBSERVACIONES DEL TÉCNICO'
    ws[f'A{obs_row}'].font = header_font

    completed = sum(1 for s in steps if s.get('status') == 'completed')
    failed = sum(1 for s in steps if s.get('status') == 'failed')
    total_time = sum(s.get('elapsed', 0) for s in steps)

    ws[f'A{obs_row + 1}'] = (
        f'Mantenimiento lógico preventivo ejecutado por CleanCPU v{Config.APP_VERSION}. '
        f'{completed}/{len(steps)} pasos completados, {failed} fallidos. '
        f'Tiempo total: {total_time:.0f}s.'
    )

    # Column widths
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 50


def _fill_form_fields(ws, system_info, steps, date_display):
    """Try to fill known cells in an existing template by searching for labels."""
    # Simple cell-value fill for known positions
    # This is a best-effort approach that works whether or not a template was loaded
    field_map = {
        'Fecha de Solicitud': date_display,
        'Fecha de Emisión': date_display,
    }

    for row in ws.iter_rows(max_row=min(50, ws.max_row or 50)):
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                val = cell.value.strip()
                if val in field_map:
                    # Fill adjacent cell
                    next_col = cell.column + 1
                    ws.cell(row=cell.row, column=next_col, value=field_map[val])


def generate_full_report(session_data):
    """
    Generate all reports after maintenance completion.
    Returns a summary of all report generation attempts.
    """
    from routes.maintenance import _collect_system_info
    system_info = _collect_system_info()
    steps = session_data.get('steps', [])

    results = {}

    # 1. HTML report
    html = generate_html_report(system_info, steps, session_data)
    local_path = save_report_locally(html, system_info)
    results['html_local'] = {'status': 'success', 'path': local_path} if local_path else {'status': 'error'}

    # 2. Network share
    results['network_share'] = save_to_network_share(html, system_info)

    # 3. Google Sheets
    results['google_sheets'] = update_google_sheets(system_info, steps)

    # 4. RADEC Excel form
    results['excel_form'] = generate_radec_excel(system_info, steps)

    return results
