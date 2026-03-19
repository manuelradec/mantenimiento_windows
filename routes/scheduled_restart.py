"""Scheduled restart CRUD routes."""
import logging
from flask import Blueprint, render_template, jsonify, request

from services.command_runner import run_powershell, CommandStatus

scheduled_restart_bp = Blueprint('scheduled_restart', __name__)
logger = logging.getLogger('cleancpu.scheduled_restart')

TASK_NAME = 'CleanCPU_Restart'


@scheduled_restart_bp.route('/')
def index():
    return render_template('scheduled_restart.html')


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
        f"    nextRun = if ($info.NextRunTime) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ 'N/A' }}; "
        f"    description = $t.Description; "
        f"    triggers = @($t.Triggers | ForEach-Object {{ $_.ToString() }}) "
        f"  }} | ConvertTo-Json -Compress "
        f"}} else {{ "
        f"  @{{ exists = $false }} | ConvertTo-Json -Compress "
        f"}}",
        description='Check scheduled restart task',
    )

    import json
    try:
        if result.output:
            data = json.loads(result.output)
            return jsonify(data)
    except (json.JSONDecodeError, ValueError):
        pass

    return jsonify({'exists': False})


@scheduled_restart_bp.route('/api/create', methods=['POST'])
def api_create():
    """Create or update the scheduled restart task."""
    data = request.get_json(silent=True) or {}
    date_str = data.get('date', '')
    time_str = data.get('time', '')
    recurrence = data.get('recurrence', 'Once')

    if not date_str or not time_str:
        return jsonify({'status': 'error', 'error': 'Fecha y hora son obligatorios.'}), 400

    datetime_str = f"{date_str} {time_str}"

    # Validate date is not in the past
    from datetime import datetime
    try:
        scheduled_dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        if recurrence == 'Once' and scheduled_dt < datetime.now():
            return jsonify({'status': 'error', 'error': 'No se puede programar en el pasado.'}), 400
    except ValueError:
        return jsonify({'status': 'error', 'error': 'Formato de fecha/hora no válido.'}), 400

    # Map recurrence to trigger parameter
    trigger_map = {
        'Once': '-Once',
        'Daily': '-Daily',
        'Weekly': '-Weekly',
        'Monthly': '',  # Monthly requires additional params
    }
    trigger_flag = trigger_map.get(recurrence, '-Once')
    if recurrence == 'Monthly':
        trigger_flag = "-Daily -DaysInterval 30"  # Approximate monthly

    ps_script = (
        f"$action = New-ScheduledTaskAction -Execute 'shutdown.exe' -Argument '/r /f /t 0'; "
        f"$trigger = New-ScheduledTaskTrigger -At '{datetime_str}' {trigger_flag}; "
        f"$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        f"-DontStopIfGoingOnBatteries; "
        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false "
        f"-ErrorAction SilentlyContinue; "
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action "
        f"-Trigger $trigger -Settings $settings -User 'SYSTEM' "
        f"-RunLevel Highest -Force -Description 'Reinicio programado por CleanCPU'"
    )

    result = run_powershell(
        ps_script,
        requires_admin=True,
        timeout=30,
        description='Create scheduled restart task',
    )

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING):
        return jsonify({
            'status': 'success',
            'message': f'Reinicio programado para {datetime_str} ({recurrence}).',
        })
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
        return jsonify({'status': 'success', 'message': 'Tarea de reinicio eliminada.'})
    else:
        return jsonify({
            'status': 'error',
            'error': result.error or 'No se pudo eliminar la tarea.',
        })
