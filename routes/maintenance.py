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
        'name': 'Auditoría de Seguridad',
        'description': 'Inspección interna: Defender, Firewall, registro, tareas, TEMP, UAC, RDP',
    },
    {
        'id': 'ccleaner',
        'name': 'Limpieza Interna del Sistema',
        'description': 'Limpieza nativa: TEMP, Windows Temp, Prefetch, cache DNS e Internet',
    },
    {
        'id': 'advancedsystemcare',
        'name': 'Salud y Reparación del Sistema',
        'description': 'DISM CheckHealth, SFC /scannow, servicios críticos, reinicio pendiente, actualizaciones',
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
                # Propagate structured data for reporting (findings, actions, etc.)
                for key in ('findings', 'actions_executed', 'space_freed_mb',
                            'repairs', 'errors', 'warnings', 'recommended_actions',
                            'admin_skipped'):
                    if key in result:
                        step_info[key] = result[key]
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
    """Internal security inspection — replaces MalwareBytes dependency."""
    from services.security_audit import run_security_audit
    return run_security_audit()


def _step_ccleaner():
    """Internal native cleanup — replaces CCleaner dependency."""
    from datetime import datetime as _dt
    from services.cleanup import (
        clean_user_temp, clean_windows_temp, clean_prefetch,
        clean_inet_cache, flush_dns_cache,
    )

    started_at = _dt.now()
    actions_executed = []
    total_freed_mb = 0.0
    errors = []

    cleanup_tasks = [
        ('Temp de usuario (%TEMP%)', clean_user_temp),
        ('Temp de Windows (Win\\Temp)', clean_windows_temp),
        ('Prefetch', clean_prefetch),
        ('Cache de Internet (INetCache)', clean_inet_cache),
        ('Cache DNS', flush_dns_cache),
    ]

    for label, func in cleanup_tasks:
        try:
            r = func()
            freed = (r.details or {}).get('freed_mb', 0) if hasattr(r, 'details') else 0
            freed = freed or 0
            total_freed_mb += freed
            action_entry = {
                'action': label,
                'status': r.status.value if hasattr(r.status, 'value') else str(r.status),
                'freed_mb': round(freed, 2),
                'detail': (r.output or ''),
            }
            if r.is_error:
                errors.append(f'{label}: {r.error or "error"}')
        except Exception as e:
            action_entry = {
                'action': label,
                'status': 'error',
                'freed_mb': 0,
                'detail': str(e),
            }
            errors.append(f'{label}: {e}')
        actions_executed.append(action_entry)

    ended_at = _dt.now()
    duration = (ended_at - started_at).total_seconds()
    total_freed_mb = round(total_freed_mb, 2)

    message = (
        f'Limpieza completada: {total_freed_mb} MB liberados '
        f'en {len(actions_executed)} operaciones.'
    )
    if errors:
        message += f' ({len(errors)} operacion(es) con error menor).'

    return {
        'status': 'completed',
        'message': message,
        'actions_executed': actions_executed,
        'space_freed_mb': total_freed_mb,
        'errors': errors,
        'warnings': [],
        'started_at': started_at.isoformat(),
        'ended_at': ended_at.isoformat(),
        'duration': round(duration, 1),
    }


def _step_advancedsystemcare():
    """Internal system health & repair module — replaces Advanced SystemCare dependency."""
    import shutil as _shutil
    from datetime import datetime as _dt
    from services.command_runner import (
        run_cmd as _run_cmd,
        run_powershell as _run_ps,
    )

    started_at = _dt.now()
    findings = []
    actions_executed = []
    repairs = []
    errors = []
    warnings = []
    recommended_actions = []
    admin_skipped = []  # tools that could not run due to missing admin rights

    def _finding(title, severity, evidence, action=''):
        return {'title': title, 'severity': severity,
                'evidence': str(evidence)[:400], 'recommended_action': action}

    # ------------------------------------------------------------------
    # 1. Pending reboot detection (multiple registry locations)
    # ------------------------------------------------------------------
    r = _run_ps(
        "$rb = $false; "
        "if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion"
        "\\Component Based Servicing\\RebootPending') { $rb = $true }; "
        "if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion"
        "\\WindowsUpdate\\Auto Update\\RebootRequired') { $rb = $true }; "
        "$pfr = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control"
        "\\Session Manager' -Name PendingFileRenameOperations "
        "-ErrorAction SilentlyContinue).PendingFileRenameOperations; "
        "if ($pfr) { $rb = $true }; "
        "$rb",
        timeout=10,
        description='Pending reboot check',
    )
    if (r.output or '').strip().lower() == 'true':
        findings.append(_finding(
            'Reinicio del sistema pendiente',
            'warning',
            'Clave RebootPending o RebootRequired encontrada en registro',
            'Reinicie el equipo para completar actualizaciones o cambios pendientes.',
        ))
        recommended_actions.append('Reiniciar el equipo (reinicio pendiente detectado)')
    else:
        findings.append(_finding(
            'Sin reinicio pendiente',
            'info',
            'No se detectaron claves de reinicio pendiente en registro',
        ))

    # ------------------------------------------------------------------
    # 2. Disk space check (C:)
    # ------------------------------------------------------------------
    try:
        total, used, free = _shutil.disk_usage('C:\\')
        free_gb = round(free / (1024 ** 3), 1)
        used_pct = round(used / total * 100, 1)
        if free_gb < 5:
            findings.append(_finding(
                f'Disco C: critico — solo {free_gb} GB libres ({100 - used_pct:.1f}% libre)',
                'critical',
                f'Total: {round(total / (1024 ** 3), 1)} GB | Usado: {round(used / (1024 ** 3), 1)} GB '
                f'| Libre: {free_gb} GB',
                'Libere espacio en C: urgentemente (elimine archivos grandes, '
                'vacie papelera, desinstale programas).',
            ))
            recommended_actions.append('Liberar espacio urgente en disco C:')
        elif free_gb < 15:
            findings.append(_finding(
                f'Disco C: espacio bajo — {free_gb} GB libres ({100 - used_pct:.1f}% libre)',
                'warning',
                f'Libre: {free_gb} GB de {round(total / (1024 ** 3), 1)} GB totales',
                'Considere limpiar archivos o ampliar el almacenamiento.',
            ))
            recommended_actions.append('Revisar espacio disponible en disco C:')
        else:
            findings.append(_finding(
                f'Disco C: espacio adecuado — {free_gb} GB libres ({100 - used_pct:.1f}% libre)',
                'info',
                f'Libre: {free_gb} GB de {round(total / (1024 ** 3), 1)} GB totales',
            ))
    except Exception as e:
        errors.append(f'Espacio en disco: {e}')

    # ------------------------------------------------------------------
    # 3. Critical Windows services status
    # ------------------------------------------------------------------
    critical_services = [
        'WinDefend', 'mpssvc', 'EventLog', 'wuauserv',
        'Dhcp', 'Dnscache', 'LanmanWorkstation',
    ]
    svc_names = ','.join(f"'{s}'" for s in critical_services)
    r = _run_ps(
        f"Get-Service -Name {svc_names} -ErrorAction SilentlyContinue "
        "| Where-Object { $_.Status -ne 'Running' } "
        "| ForEach-Object { \"$($_.Name)|$($_.Status)|$($_.DisplayName)\" }",
        timeout=15,
        description='Critical services status check',
    )
    stopped = []
    for line in (r.output or '').splitlines():
        line = line.strip()
        if '|' not in line:
            continue
        parts = line.split('|', 2)
        stopped.append({
            'name': parts[0],
            'status': parts[1] if len(parts) > 1 else '',
            'display': parts[2] if len(parts) > 2 else parts[0],
        })

    if stopped:
        for svc in stopped:
            findings.append(_finding(
                f'Servicio critico detenido: {svc["display"]}',
                'warning',
                f'{svc["name"]}: {svc["status"]}',
                f'Verifique e inicie el servicio {svc["name"]} si es necesario.',
            ))
        recommended_actions.append(
            f'Revisar {len(stopped)} servicio(s) critico(s) detenidos'
        )
    else:
        findings.append(_finding(
            'Servicios criticos del sistema: todos activos',
            'info',
            f'Verificados: {", ".join(critical_services)}',
        ))

    # ------------------------------------------------------------------
    # 4. DISM CheckHealth (fast — does not repair, reads flag only)
    # ------------------------------------------------------------------
    r = _run_cmd(
        ['dism', '/Online', '/Cleanup-Image', '/CheckHealth'],
        requires_admin=True,
        timeout=120,
        description='DISM CheckHealth',
    )
    dism_out = (r.output or '').lower()
    actions_executed.append({
        'action': 'DISM /CheckHealth',
        'status': r.status.value if hasattr(r.status, 'value') else str(r.status),
        'detail': (r.output or r.error or '')[:600],
    })
    if r.status.value == 'requires_admin':
        admin_skipped.append('DISM /CheckHealth')
        warnings.append('DISM /CheckHealth omitido: se requiere ejecutar como Administrador')
        findings.append(_finding(
            'DISM: omitido — se requiere ejecutar como Administrador',
            'warning',
            'El proceso actual no tiene privilegios de administrador',
            'Ejecute el mantenimiento como Administrador para habilitar DISM.',
        ))
    elif r.is_error:
        errors.append(f'DISM CheckHealth: {r.error or "error"}')
        findings.append(_finding(
            'DISM: no se pudo ejecutar la verificacion',
            'warning',
            r.error or 'DISM retorno error',
            'Ejecute DISM /Online /Cleanup-Image /CheckHealth con permisos de administrador.',
        ))
    elif 'repairable' in dism_out:
        findings.append(_finding(
            'DISM: imagen del sistema marcada como reparable',
            'warning',
            'DISM /CheckHealth reporto bandera de reparacion',
            'Ejecute: DISM /Online /Cleanup-Image /RestoreHealth',
        ))
        recommended_actions.append('Ejecutar DISM /RestoreHealth para reparar imagen')
    else:
        findings.append(_finding(
            'DISM: imagen del sistema sin corrupcion detectada',
            'info',
            'DISM /CheckHealth: sin banderas de reparacion',
        ))

    # ------------------------------------------------------------------
    # 5. SFC /scannow (verifies and repairs Windows system files)
    # ------------------------------------------------------------------
    r = _run_cmd(
        ['sfc', '/scannow'],
        requires_admin=True,
        timeout=900,
        description='SFC integrity scan',
    )
    sfc_out = (r.output or '').lower()
    actions_executed.append({
        'action': 'SFC /scannow',
        'status': r.status.value if hasattr(r.status, 'value') else str(r.status),
        'detail': (r.output or '')[:600],
    })
    if r.status.value == 'requires_admin':
        admin_skipped.append('SFC /scannow')
        warnings.append('SFC /scannow omitido: se requiere ejecutar como Administrador')
        findings.append(_finding(
            'SFC: omitido — se requiere ejecutar como Administrador',
            'warning',
            'El proceso actual no tiene privilegios de administrador',
            'Ejecute el mantenimiento como Administrador para habilitar SFC /scannow.',
        ))
    elif r.is_error:
        errors.append(f'SFC: {r.error or "error"}')
        findings.append(_finding(
            'SFC: error al ejecutar la verificacion',
            'warning',
            r.error or 'SFC retorno codigo de error',
            'Ejecute sfc /scannow desde una terminal con permisos de administrador.',
        ))
    elif ('did not find any integrity violations' in sfc_out
          or 'no encontr' in sfc_out
          or 'no integrity violations' in sfc_out):
        findings.append(_finding(
            'SFC: archivos del sistema integros — sin infracciones',
            'info',
            'sfc /scannow: no se encontraron violaciones de integridad',
        ))
        repairs.append('SFC verifico integridad del sistema sin problemas')
    elif ('successfully repaired' in sfc_out
          or 'reparo correctamente' in sfc_out
          or 'reparados correctamente' in sfc_out):
        findings.append(_finding(
            'SFC: archivos del sistema reparados exitosamente',
            'info',
            'sfc /scannow: archivos danados detectados y reparados',
        ))
        repairs.append('SFC reparo archivos del sistema correctamente')
    elif 'found integrity violations' in sfc_out or 'infracciones' in sfc_out:
        findings.append(_finding(
            'SFC: infracciones de integridad detectadas y NO reparadas',
            'warning',
            'sfc /scannow reporto archivos danados que no pudo reparar',
            'Ejecute DISM /RestoreHealth y luego repita sfc /scannow.',
        ))
        recommended_actions.append('Ejecutar DISM /RestoreHealth y repetir SFC')
    else:
        findings.append(_finding(
            'SFC completado',
            'info',
            (r.output or '')[:200],
        ))

    # ------------------------------------------------------------------
    # 6. Startup programs (impact review)
    # ------------------------------------------------------------------
    r = _run_ps(
        "Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue "
        "| Select-Object Name, Location "
        "| ForEach-Object { \"$($_.Name)|$($_.Location)\" } "
        "| Select-Object -First 25",
        timeout=15,
        description='Startup programs impact review',
    )
    startup_entries = []
    for line in (r.output or '').splitlines():
        line = line.strip()
        if '|' not in line:
            continue
        parts = line.split('|', 1)
        startup_entries.append({
            'name': parts[0],
            'location': parts[1] if len(parts) > 1 else '',
        })

    if startup_entries:
        findings.append(_finding(
            f'Inicio automatico: {len(startup_entries)} programa(s) registrado(s)',
            'info',
            ' | '.join(
                f'{e["name"]} ({e["location"]})' for e in startup_entries[:6]
            ),
        ))
    else:
        findings.append(_finding(
            'Inicio automatico: sin programas registrados',
            'info',
            'Win32_StartupCommand: sin entradas',
        ))

    # ------------------------------------------------------------------
    # 7. Pending Windows Updates (via Windows Update Agent COM object)
    # ------------------------------------------------------------------
    r = _run_ps(
        "try { "
        "  $s = New-Object -ComObject Microsoft.Update.Session -ErrorAction Stop; "
        "  $r = $s.CreateUpdateSearcher().Search("
        "    'IsInstalled=0 and Type=\\'Software\\' and IsHidden=0'); "
        "  $r.Updates.Count "
        "} catch { '-1' }",
        timeout=45,
        description='Pending Windows Updates check',
    )
    pending_raw = (r.output or '').strip()
    try:
        pending = int(pending_raw)
        if pending > 0:
            findings.append(_finding(
                f'{pending} actualizacion(es) de Windows pendiente(s)',
                'warning',
                f'Windows Update Agent: {pending} actualizaciones sin instalar',
                'Instale las actualizaciones pendientes desde Windows Update.',
            ))
            recommended_actions.append('Instalar actualizaciones pendientes de Windows')
        elif pending == 0:
            findings.append(_finding(
                'Windows Update: sin actualizaciones pendientes',
                'info',
                'Windows Update Agent: el sistema esta al dia',
            ))
        # -1 means COM query failed — skip silently (not all configs support it)
    except (ValueError, TypeError):
        warnings.append('No se pudo consultar actualizaciones pendientes via COM')

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    ended_at = _dt.now()
    duration = (ended_at - started_at).total_seconds()

    critical_count = sum(1 for f in findings if f.get('severity') == 'critical')
    warning_count = sum(1 for f in findings if f.get('severity') == 'warning')

    if critical_count > 0:
        message = (
            f'Salud del sistema: {critical_count} problema(s) CRITICO(S) — '
            f'{warning_count} advertencia(s). Atencion inmediata requerida.'
        )
    elif warning_count > 0:
        message = (
            f'Salud del sistema: {warning_count} advertencia(s). '
            f'{len(repairs)} reparacion(es) completada(s) por SFC/DISM.'
        )
    else:
        message = (
            f'Salud del sistema: buena. DISM y SFC sin problemas. '
            f'{len(actions_executed)} herramienta(s) ejecutada(s).'
        )
    if admin_skipped:
        message += (
            f' ATENCION: {", ".join(admin_skipped)} no se ejecutaron — '
            'se requieren permisos de Administrador.'
        )
    if errors:
        message += f' ({len(errors)} error(es) menores).'

    return {
        'status': 'completed',
        'message': message,
        'findings': findings,
        'actions_executed': actions_executed,
        'repairs': repairs,
        'errors': errors,
        'warnings': warnings,
        'admin_skipped': admin_skipped,
        'started_at': started_at.isoformat(),
        'ended_at': ended_at.isoformat(),
        'duration': round(duration, 1),
        'recommended_actions': recommended_actions,
    }


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
    # TEMP, Windows\Temp y Prefetch ya fueron limpiados en _step_ccleaner (paso 2).
    # Ejecutar de nuevo en la misma sesion no aporta nada y duplica el tiempo.
    return {
        'status': 'skipped',
        'message': (
            'TEMP, Windows\\Temp y Prefetch ya fueron limpiados en '
            '"Limpieza Interna del Sistema". Omitido para evitar duplicacion.'
        ),
    }


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
    # SFC /scannow ya fue ejecutado en _step_advancedsystemcare (paso 3).
    # Repetirlo en la misma sesion duplica hasta 15 minutos de escaneo innecesario.
    return {
        'status': 'skipped',
        'message': (
            'SFC /scannow ya fue ejecutado en "Salud y Reparacion del Sistema". '
            'Omitido para evitar duplicacion.'
        ),
    }


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
    """Collect comprehensive system hardware info for RADEC reports."""
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

    # Detailed RAM info (type and speed)
    r = run_powershell(
        "Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1 "
        "Speed, ConfiguredClockSpeed, SMBIOSMemoryType | "
        "ForEach-Object { "
        "$type = switch($_.SMBIOSMemoryType) { "
        "20 {'DDR'} 21 {'DDR2'} 24 {'DDR3'} 26 {'DDR4'} 34 {'DDR5'} "
        "default {'DDR'} }; "
        "\"$type-$($_.ConfiguredClockSpeed)\" }",
        timeout=10, description='Get RAM type',
    )
    ram_type = (r.output or '').strip() if r.output else ''
    if ram_type:
        info['ram_detail'] = f"{info['ram_gb']} {ram_type}"
    else:
        info['ram_detail'] = info['ram_gb']

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
        "BusType, @{N='SizeGB';E={[math]::Round($_.Size/1GB,0)}} | "
        "ForEach-Object { \"$($_.SizeGB) GB $($_.BusType) $($_.MediaType)\" }",
        timeout=10, description='Get disk info',
    )
    info['hard_drive'] = (r.output or '').strip() if r.output else 'N/A'

    # OS version
    r = run_powershell(
        "(Get-WmiObject Win32_OperatingSystem).Caption",
        timeout=10, description='Get OS version',
    )
    info['os_version'] = (r.output or '').strip() if r.output else 'N/A'

    # OS build (display version like 25H2)
    r = run_powershell(
        "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').DisplayVersion",
        timeout=10, description='Get OS display version',
    )
    os_display = (r.output or '').strip() if r.output else ''
    if os_display:
        info['os_version_full'] = f"{info['os_version']} {os_display}"
    else:
        info['os_version_full'] = info['os_version']

    # Monitor info
    r = run_powershell(
        "Get-CimInstance WmiMonitorID -Namespace root/wmi -ErrorAction SilentlyContinue | "
        "Select-Object -First 1 | ForEach-Object { "
        "$mfr = ($_.ManufacturerName | Where-Object {$_ -ne 0} | "
        "ForEach-Object {[char]$_}) -join ''; "
        "$model = ($_.UserFriendlyName | Where-Object {$_ -ne 0} | "
        "ForEach-Object {[char]$_}) -join ''; "
        "$serial = ($_.SerialNumberID | Where-Object {$_ -ne 0} | "
        "ForEach-Object {[char]$_}) -join ''; "
        "\"$mfr|$model|$serial\" }",
        timeout=15, description='Get monitor info',
    )
    monitor_raw = (r.output or '').strip() if r.output else ''
    if monitor_raw and '|' in monitor_raw:
        parts = monitor_raw.split('|')
        info['monitor_manufacturer'] = parts[0] if len(parts) > 0 else 'N/A'
        info['monitor_model'] = parts[1] if len(parts) > 1 else 'N/A'
        info['monitor_serial'] = parts[2] if len(parts) > 2 else 'N/A'
        info['monitor_info'] = f"{parts[0]} MOD:{parts[1]} S/N: {parts[2]}"
    else:
        info['monitor_info'] = 'N/A'
        info['monitor_manufacturer'] = 'N/A'
        info['monitor_model'] = 'N/A'
        info['monitor_serial'] = 'N/A'

    # System serial with additional IDs (asset tags)
    r = run_powershell(
        "$bios = Get-WmiObject Win32_BIOS; "
        "$cs = Get-WmiObject Win32_ComputerSystem; "
        "$enc = Get-WmiObject Win32_SystemEnclosure; "
        "\"$($bios.SerialNumber), $($enc.SMBIOSAssetTag), $($cs.DNSHostName)\"",
        timeout=10, description='Get serial and asset info',
    )
    info['serial_full'] = (r.output or '').strip() if r.output else info.get('serial', 'N/A')

    # Equipment description (model + serial for FO-TI-19)
    info['equipment_description'] = (
        f"{info.get('model', 'N/A')}, N/S: {info.get('serial', 'N/A')}"
    )

    # Detect optical drives
    r = run_powershell(
        "Get-CimInstance Win32_CDROMDrive -ErrorAction SilentlyContinue | "
        "Select-Object Name, MediaType | ConvertTo-Json",
        timeout=10, description='Get optical drives',
    )
    info['has_cdrom'] = False
    info['has_dvdrom'] = False
    if r.output and r.output.strip():
        cd_raw = r.output.strip().lower()
        info['has_cdrom'] = 'cd' in cd_raw
        info['has_dvdrom'] = 'dvd' in cd_raw

    # Detect USB ports
    info['has_usb'] = True  # Practically all PCs have USB
    info['has_micro_sd'] = False  # Will be detected if card reader present
    r = run_powershell(
        "Get-PnpDevice -Class 'SDHost' -Status OK -ErrorAction SilentlyContinue | "
        "Measure-Object | Select-Object -ExpandProperty Count",
        timeout=10, description='Detect SD card reader',
    )
    sd_count = (r.output or '').strip()
    if sd_count and sd_count.isdigit() and int(sd_count) > 0:
        info['has_micro_sd'] = True

    # Logged-in user full name
    r = run_powershell(
        "try { (Get-CimInstance Win32_UserAccount | "
        "Where-Object { $_.Name -eq $env:USERNAME } | "
        "Select-Object -First 1).FullName } catch { $env:USERNAME }",
        timeout=10, description='Get user full name',
    )
    info['user_fullname'] = (r.output or '').strip() if r.output else 'N/A'

    # User email from Active Directory (if domain joined)
    r = run_powershell(
        "try { ([adsisearcher]\"(&(objectCategory=User)"
        "(samAccountName=$env:USERNAME))\").FindOne().Properties.mail } "
        "catch { 'N/A' }",
        timeout=10, description='Get user email',
    )
    info['user_email'] = (r.output or '').strip() if r.output else 'N/A'

    # Get upgrade opportunities
    try:
        from services.system_info import get_upgrade_opportunities
        info['upgrade_opportunities'] = get_upgrade_opportunities()
    except Exception as e:
        logger.warning(f"Failed to get upgrade opportunities: {e}")
        info['upgrade_opportunities'] = {'recommendations': []}

    return info
