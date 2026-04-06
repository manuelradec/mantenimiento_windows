"""Scheduled restart routes — Phase 7 safety improvements.

Changes from Phase 7:
- /r /f /t 0 removed from the default (normal) restart path.
- Grace period (1/5/15/30/60 min) is now configurable.
- Forced restart (/f) requires explicit force=True + force_confirmed=True in the
  request body — a double-lock that mirrors the two-step UI confirmation.
- Uptime endpoint added so the technician can see whether the machine is in use.
- All restart decisions are logged with a [NORMAL] or [FORCE] tag.
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request

from services.command_runner import run_powershell, CommandStatus

scheduled_restart_bp = Blueprint('scheduled_restart', __name__)
logger = logging.getLogger('cleancpu.scheduled_restart')

TASK_NAME = 'CleanCPU_Restart'

# Allowed grace periods (minutes). Validated server-side; any other value is rejected.
_ALLOWED_GRACE = {1, 5, 15, 30, 60}


@scheduled_restart_bp.route('/')
def index():
    return render_template('scheduled_restart.html')


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------

@scheduled_restart_bp.route('/api/uptime')
def api_uptime():
    """Return machine uptime using Get-CimInstance Win32_OperatingSystem."""
    result = run_powershell(
        '$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; '
        '$span = (Get-Date) - $boot; '
        '[ordered]@{ '
        '  days    = $span.Days; '
        '  hours   = $span.Hours; '
        '  minutes = $span.Minutes; '
        '  boot_time = $boot.ToString("yyyy-MM-dd HH:mm") '
        '} | ConvertTo-Json -Compress',
        timeout=15,
        description='Query system uptime',
    )

    if result.output:
        try:
            data = json.loads(result.output)
            return jsonify({'status': 'success', **data})
        except (json.JSONDecodeError, ValueError):
            pass

    return jsonify({
        'status': 'error',
        'message': 'No se pudo leer el tiempo de actividad.',
        'days': None, 'hours': None, 'minutes': None, 'boot_time': None,
    })


@scheduled_restart_bp.route('/api/status')
def api_status():
    """Check if the scheduled restart task exists and return its config."""
    result = run_powershell(
        f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($t) {{ "
        f"  $info = $t | Get-ScheduledTaskInfo; "
        f"  @{{ "
        f"    exists = $true; "
        f"    state = $t.State.ToString(); "
        f"    nextRun = if ($info.NextRunTime) "
        f"      {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ 'N/A' }}; "
        f"    description = $t.Description; "
        f"    triggers = @($t.Triggers | ForEach-Object {{ $_.ToString() }}) "
        f"  }} | ConvertTo-Json -Compress "
        f"}} else {{ "
        f"  @{{ exists = $false }} | ConvertTo-Json -Compress "
        f"}}",
        description='Check scheduled restart task',
    )

    try:
        if result.output:
            data = json.loads(result.output)
            return jsonify(data)
    except (json.JSONDecodeError, ValueError):
        pass

    return jsonify({'exists': False})


# ---------------------------------------------------------------------------
# Mutating endpoints
# ---------------------------------------------------------------------------

@scheduled_restart_bp.route('/api/create', methods=['POST'])
def api_create():
    """
    Create or update the scheduled restart task.

    Normal path  (force=False, default):
        shutdown.exe /r /t <grace_seconds>
        Windows shows a countdown dialog to the logged-in user.
        grace_period: 1 | 5 | 15 | 30 | 60  (minutes, required)

    Forced path  (force=True):
        shutdown.exe /r /f /t 0
        All applications are terminated immediately without warning.
        Requires BOTH force=True AND force_confirmed=True in the request body.
        The UI must collect two explicit confirmations before sending these flags.
    """
    data = request.get_json(silent=True) or {}
    date_str = data.get('date', '').strip()
    time_str = data.get('time', '').strip()
    recurrence = data.get('recurrence', 'Once')
    grace_period = data.get('grace_period', 5)   # minutes, normal path only
    force = bool(data.get('force', False))
    force_confirmed = bool(data.get('force_confirmed', False))

    # --- Basic input validation ---
    if not date_str or not time_str:
        return jsonify({'status': 'error', 'error': 'Fecha y hora son obligatorios.'}), 400

    datetime_str = f'{date_str} {time_str}'
    try:
        scheduled_dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        if recurrence == 'Once' and scheduled_dt < datetime.now():
            return jsonify({'status': 'error',
                            'error': 'No se puede programar en el pasado.'}), 400
    except ValueError:
        return jsonify({'status': 'error',
                        'error': 'Formato de fecha/hora no válido.'}), 400

    # --- Force path double-lock ---
    if force:
        if not force_confirmed:
            logger.warning(
                '[REJECT] Force restart attempted without force_confirmed flag '
                'for task at %s', datetime_str,
            )
            return jsonify({
                'status': 'error',
                'error': (
                    'Reinicio forzado requiere confirmación explícita '
                    '(force_confirmed=true). '
                    'Use el formulario de reinicio forzado en la interfaz.'
                ),
            }), 400
        logger.warning(
            '[FORCE] Forced restart scheduled: %s, recurrence=%s — '
            'machine may be in active use',
            datetime_str, recurrence,
        )
        shutdown_args = '/r /f /t 0'
        description_tag = '[FORZADO] Reinicio forzado por CleanCPU'
    else:
        # Normal path: validate grace period
        try:
            grace_period = int(grace_period)
        except (ValueError, TypeError):
            grace_period = 5
        if grace_period not in _ALLOWED_GRACE:
            return jsonify({
                'status': 'error',
                'error': (
                    f'Período de gracia no válido: {grace_period}. '
                    f'Valores permitidos: {sorted(_ALLOWED_GRACE)} minutos.'
                ),
            }), 400
        grace_seconds = grace_period * 60
        logger.info(
            '[NORMAL] Restart scheduled: %s, grace=%dmin, recurrence=%s',
            datetime_str, grace_period, recurrence,
        )
        shutdown_args = f'/r /t {grace_seconds}'
        description_tag = (
            f'[NORMAL] Reinicio programado por CleanCPU '
            f'(aviso {grace_period} min)'
        )

    # --- Recurrence trigger ---
    trigger_map = {
        'Once': '-Once',
        'Daily': '-Daily',
        'Weekly': '-Weekly',
        'Monthly': '-Daily -DaysInterval 30',
    }
    trigger_flag = trigger_map.get(recurrence, '-Once')

    ps_script = (
        f"$action = New-ScheduledTaskAction "
        f"  -Execute 'shutdown.exe' -Argument '{shutdown_args}'; "
        f"$trigger = New-ScheduledTaskTrigger -At '{datetime_str}' {trigger_flag}; "
        f"$settings = New-ScheduledTaskSettingsSet "
        f"  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false "
        f"  -ErrorAction SilentlyContinue; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action "
        f"  -Trigger $trigger -Settings $settings -User 'SYSTEM' "
        f"  -RunLevel Highest -Force "
        f"  -Description '{description_tag}'"
    )

    result = run_powershell(
        ps_script,
        requires_admin=True,
        timeout=30,
        description='Create scheduled restart task',
    )

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING):
        if force:
            msg = (
                f'Reinicio FORZADO programado para {datetime_str} ({recurrence}). '
                'No habrá aviso al usuario — todos los programas se cerrarán.'
            )
        else:
            msg = (
                f'Reinicio programado para {datetime_str} ({recurrence}). '
                f'Se mostrará un aviso de {grace_period} min al usuario.'
            )
        return jsonify({'status': 'success', 'message': msg})
    else:
        return jsonify({
            'status': 'error',
            'error': result.error or 'No se pudo crear la tarea programada.',
        })


@scheduled_restart_bp.route('/api/delete', methods=['POST'])
def api_delete():
    """Delete the scheduled restart task."""
    result = run_powershell(
        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false",
        requires_admin=True,
        timeout=15,
        description='Delete scheduled restart task',
    )

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING):
        logger.info('[DELETE] Scheduled restart task deleted.')
        return jsonify({'status': 'success', 'message': 'Tarea de reinicio eliminada.'})
    else:
        return jsonify({
            'status': 'error',
            'error': result.error or 'No se pudo eliminar la tarea.',
        })
