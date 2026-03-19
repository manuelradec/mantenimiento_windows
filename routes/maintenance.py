"""Logical Maintenance (Mantenimiento Logico) routes."""
import logging
import time
import threading
import uuid
from datetime import datetime

from flask import Blueprint, render_template, jsonify

from services.command_runner import run_powershell, run_cmd

maintenance_bp = Blueprint('maintenance', __name__)
logger = logging.getLogger('cleancpu.maintenance')

# In-memory store for active maintenance sessions
_sessions = {}
_sessions_lock = threading.Lock()

MAINTENANCE_STEPS = [
    {
        'id': 'malwarebytes',
        'name': 'Escaneo MalwareBytes',
        'description': 'Ejecutar escaneo de amenazas con MalwareBytes',
    },
    {
        'id': 'ccleaner',
        'name': 'Optimización CCleaner',
        'description': 'Ejecutar limpieza automática con CCleaner',
    },
    {
        'id': 'advancedsystemcare',
        'name': 'Advanced SystemCare',
        'description': 'Ejecutar escaneo y reparación con Advanced SystemCare',
    },
    {
        'id': 'defrag',
        'name': 'Desfragmentación de disco',
        'description': 'Desfragmentar HDD o TRIM SSD',
    },
    {
        'id': 'temp_cleanup',
        'name': 'Eliminar archivos temporales',
        'description': 'Limpiar TEMP, Windows\\Temp y Prefetch',
    },
    {
        'id': 'disk_cleanup',
        'name': 'Limpieza del disco del sistema',
        'description': 'Ejecutar limpieza de disco de Windows en C:',
    },
    {
        'id': 'sfc',
        'name': 'Escaneo SFC',
        'description': 'Verificar integridad de archivos del sistema',
    },
    {
        'id': 'windows_update',
        'name': 'Verificación de Windows Update',
        'description': 'Buscar actualizaciones disponibles',
    },
    {
        'id': 'lenovo_update',
        'name': 'Verificación Lenovo Update',
        'description': 'Verificar actualizaciones de controladores Lenovo',
    },
]


@maintenance_bp.route('/')
def index():
    return render_template('maintenance.html')


@maintenance_bp.route('/api/steps')
def api_steps():
    """Return the list of maintenance steps."""
    return jsonify({'steps': MAINTENANCE_STEPS})


@maintenance_bp.route('/api/start', methods=['POST'])
def api_start():
    """Start a logical maintenance session."""
    session_id = str(uuid.uuid4())[:8]

    session = {
        'id': session_id,
        'status': 'running',
        'started_at': datetime.now().isoformat(),
        'current_step': 0,
        'steps': [],
        'cancelled': False,
    }

    for step in MAINTENANCE_STEPS:
        session['steps'].append({
            'id': step['id'],
            'name': step['name'],
            'status': 'pending',
            'elapsed': 0,
            'message': '',
            'started_at': None,
            'completed_at': None,
        })

    with _sessions_lock:
        _sessions[session_id] = session

    # Run maintenance in background thread
    thread = threading.Thread(
        target=_run_maintenance, args=(session_id,), daemon=True
    )
    thread.start()

    return jsonify({'status': 'started', 'session_id': session_id})


@maintenance_bp.route('/api/status/<session_id>')
def api_status(session_id):
    """Get status of a maintenance session."""
    with _sessions_lock:
        session = _sessions.get(session_id)

    if not session:
        return jsonify({'error': 'Sesión no encontrada.'}), 404

    return jsonify(session)


@maintenance_bp.route('/api/cancel/<session_id>', methods=['POST'])
def api_cancel(session_id):
    """Cancel a running maintenance session."""
    with _sessions_lock:
        session = _sessions.get(session_id)
        if session:
            session['cancelled'] = True
            return jsonify({'status': 'cancelling'})
    return jsonify({'error': 'Sesión no encontrada.'}), 404


@maintenance_bp.route('/api/system-info')
def api_system_info():
    """Get system hardware info for reports."""
    info = _collect_system_info()
    return jsonify(info)


@maintenance_bp.route('/api/report/<session_id>', methods=['POST'])
def api_generate_report(session_id):
    """Generate all reports for a completed maintenance session."""
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        return jsonify({'error': 'Sesión no encontrada.'}), 404

    try:
        from services.maintenance_report import generate_full_report
        results = generate_full_report(session)
        return jsonify({'status': 'success', 'reports': results})
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)})


def _run_maintenance(session_id):
    """Execute all maintenance steps sequentially."""
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        return

    handlers = {
        'malwarebytes': _step_malwarebytes,
        'ccleaner': _step_ccleaner,
        'advancedsystemcare': _step_advancedsystemcare,
        'defrag': _step_defrag,
        'temp_cleanup': _step_temp_cleanup,
        'disk_cleanup': _step_disk_cleanup,
        'sfc': _step_sfc,
        'windows_update': _step_windows_update,
        'lenovo_update': _step_lenovo_update,
    }

    for i, step_info in enumerate(session['steps']):
        if session.get('cancelled'):
            step_info['status'] = 'cancelled'
            step_info['message'] = 'Cancelado por el usuario.'
            # Mark remaining steps as cancelled
            for j in range(i + 1, len(session['steps'])):
                session['steps'][j]['status'] = 'cancelled'
                session['steps'][j]['message'] = 'Cancelado por el usuario.'
            break

        session['current_step'] = i
        step_info['status'] = 'running'
        step_info['started_at'] = datetime.now().isoformat()
        start_time = time.time()

        handler = handlers.get(step_info['id'])
        try:
            if handler:
                result = handler()
                step_info['status'] = result.get('status', 'completed')
                step_info['message'] = result.get('message', '')
            else:
                step_info['status'] = 'skipped'
                step_info['message'] = 'Sin manejador disponible.'
        except Exception as e:
            logger.error(f"Maintenance step {step_info['id']} failed: {e}")
            step_info['status'] = 'failed'
            step_info['message'] = str(e)

        step_info['elapsed'] = round(time.time() - start_time, 1)
        step_info['completed_at'] = datetime.now().isoformat()

    session['status'] = 'completed'
    session['completed_at'] = datetime.now().isoformat()
    logger.info(f"Maintenance session {session_id} completed")


# ============================================================
# Step Handlers
# ============================================================

def _check_exe_exists(paths):
    """Check if an executable exists at any of the given paths."""
    import os
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def _step_malwarebytes():
    paths = [
        r'C:\Program Files\Malwarebytes\Anti-Malware\mbam.exe',
        r'C:\Program Files (x86)\Malwarebytes\Anti-Malware\mbam.exe',
    ]
    exe = _check_exe_exists(paths)
    if not exe:
        return {'status': 'skipped', 'message': 'MalwareBytes no está instalado.'}

    run_cmd(
        f'start "" "{exe}"',
        shell=True, timeout=10,
        description='Launch MalwareBytes',
    )
    return {'status': 'completed', 'message': 'MalwareBytes iniciado. Ejecute el escaneo manualmente.'}


def _step_ccleaner():
    paths = [
        r'C:\Program Files\CCleaner\CCleaner.exe',
        r'C:\Program Files (x86)\CCleaner\CCleaner.exe',
    ]
    exe = _check_exe_exists(paths)
    if not exe:
        return {'status': 'skipped', 'message': 'CCleaner no está instalado.'}

    result = run_cmd(
        f'"{exe}" /AUTO',
        timeout=300,
        description='Run CCleaner auto-clean',
    )
    if result.is_error:
        return {'status': 'failed', 'message': result.error or 'Error al ejecutar CCleaner.'}
    return {'status': 'completed', 'message': 'CCleaner ejecutado exitosamente.'}


def _step_advancedsystemcare():
    paths = [
        r'C:\Program Files (x86)\IObit\Advanced SystemCare\ASC.exe',
        r'C:\Program Files\IObit\Advanced SystemCare\ASC.exe',
    ]
    exe = _check_exe_exists(paths)
    if not exe:
        return {'status': 'skipped', 'message': 'Advanced SystemCare no está instalado.'}

    run_cmd(
        f'start "" "{exe}"',
        shell=True, timeout=10,
        description='Launch Advanced SystemCare',
    )
    return {'status': 'completed', 'message': 'Advanced SystemCare iniciado. Ejecute el escaneo manualmente.'}


def _step_defrag():
    # Detect drive type
    detect = run_powershell(
        "Get-PhysicalDisk | Select-Object -First 1 -ExpandProperty MediaType",
        timeout=15,
        description='Detect drive type',
    )
    media_type = (detect.output or '').strip().upper()

    if 'SSD' in media_type:
        result = run_cmd(
            ['defrag', 'C:', '/L'],
            requires_admin=True, timeout=300,
            description='ReTrim SSD',
        )
        op = 'TRIM en SSD'
    else:
        result = run_cmd(
            ['defrag', 'C:', '/O'],
            requires_admin=True, timeout=600,
            description='Defragment HDD',
        )
        op = 'Desfragmentación de HDD'

    if result.is_error:
        return {'status': 'failed', 'message': f'Error en {op}: {result.error}'}
    return {'status': 'completed', 'message': f'{op} completado exitosamente.'}


def _step_temp_cleanup():
    from services.cleanup import clean_user_temp, clean_windows_temp, clean_prefetch
    results = []
    for name, func in [
        ('User Temp', clean_user_temp),
        ('Windows Temp', clean_windows_temp),
        ('Prefetch', clean_prefetch),
    ]:
        try:
            r = func()
            results.append(f"{name}: {r.status.value if hasattr(r, 'status') else 'ok'}")
        except Exception as e:
            results.append(f"{name}: error ({e})")
    return {'status': 'completed', 'message': '; '.join(results)}


def _step_disk_cleanup():
    result = run_cmd(
        'cleanmgr /sagerun:1',
        requires_admin=True, timeout=300,
        description='Disk Cleanup',
    )
    if result.is_error:
        return {'status': 'failed', 'message': result.error or 'Error en limpieza de disco.'}
    return {'status': 'completed', 'message': 'Limpieza de disco completada.'}


def _step_sfc():
    result = run_cmd(
        ['sfc', '/scannow'],
        requires_admin=True, timeout=900,
        description='SFC scan',
    )
    if result.is_error:
        return {'status': 'failed', 'message': result.error or 'Error en SFC.'}

    output = result.output or ''
    if 'no encontró ninguna infracción' in output.lower() or 'did not find any integrity' in output.lower():
        return {'status': 'completed', 'message': 'SFC: No se encontraron problemas de integridad.'}
    elif 'reparó correctamente' in output.lower() or 'successfully repaired' in output.lower():
        return {'status': 'completed', 'message': 'SFC: Se repararon archivos del sistema.'}
    return {'status': 'completed', 'message': 'SFC completado. Revise los detalles en el registro.'}


def _step_windows_update():
    run_cmd(
        'UsoClient StartScan',
        requires_admin=True, timeout=120,
        description='Scan for updates',
    )
    # Get Windows version info
    ver = run_powershell(
        "[System.Environment]::OSVersion.Version.ToString()",
        timeout=10,
        description='Get Windows version',
    )
    msg = f"Escaneo de actualizaciones completado. Windows: {(ver.output or 'N/A').strip()}"
    return {'status': 'completed', 'message': msg}


def _step_lenovo_update():
    paths = [
        r'C:\Program Files (x86)\Lenovo\VantageService\Lenovo.Vantage.exe',
        r'C:\Program Files\Lenovo\VantageService\Lenovo.Vantage.exe',
        r'C:\Program Files (x86)\Lenovo\System Update\tvsu.exe',
    ]
    exe = _check_exe_exists(paths)
    if not exe:
        return {'status': 'skipped', 'message': 'Lenovo Vantage/System Update no está instalado.'}

    run_cmd(
        f'start "" "{exe}"',
        shell=True, timeout=10,
        description='Launch Lenovo Update',
    )
    return {'status': 'completed', 'message': 'Lenovo Update iniciado. Verifique actualizaciones manualmente.'}


def _collect_system_info():
    """Collect system hardware info for reporting."""
    import sys
    info = {}
    if sys.platform != 'win32':
        return {'note': 'Solo disponible en Windows.'}

    queries = {
        'serial': "(Get-WmiObject Win32_BIOS).SerialNumber",
        'manufacturer': "(Get-WmiObject Win32_ComputerSystem).Manufacturer",
        'model': "(Get-WmiObject Win32_ComputerSystem).Model",
        'processor': "(Get-WmiObject Win32_Processor).Name",
        'ram_bytes': "(Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory",
        'hostname': "$env:COMPUTERNAME",
    }

    for key, ps in queries.items():
        r = run_powershell(ps, timeout=10, description=f'Get {key}')
        info[key] = (r.output or '').strip() if r.output else 'N/A'

    # RAM in GB
    try:
        ram_bytes = int(info.get('ram_bytes', 0))
        info['ram_gb'] = f"{round(ram_bytes / (1024**3), 1)} GB"
    except (ValueError, TypeError):
        info['ram_gb'] = info.get('ram_bytes', 'N/A')

    # IP address
    r = run_powershell(
        "(Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.InterfaceAlias -notlike '*Loopback*' } | "
        "Select-Object -First 1).IPAddress",
        timeout=10, description='Get IP',
    )
    info['ip_address'] = (r.output or '').strip() if r.output else 'N/A'

    # Hard drive
    r = run_powershell(
        "Get-PhysicalDisk | Select-Object -First 1 FriendlyName, MediaType, "
        "@{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}} | "
        "ForEach-Object { \"$($_.FriendlyName) ($($_.MediaType), $($_.SizeGB) GB)\" }",
        timeout=10, description='Get disk info',
    )
    info['hard_drive'] = (r.output or '').strip() if r.output else 'N/A'

    # OS version
    r = run_powershell(
        "(Get-WmiObject Win32_OperatingSystem).Caption + ' Build ' + "
        "(Get-WmiObject Win32_OperatingSystem).BuildNumber",
        timeout=10, description='Get OS version',
    )
    info['os_version'] = (r.output or '').strip() if r.output else 'N/A'

    return info
