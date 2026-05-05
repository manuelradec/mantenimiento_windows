"""Scheduled restart — Windows schtasks via PowerShell.

Capa de servicio: lógica de bajo nivel que la ruta invoca a través de
core.governance.execute_governed_action. Las funciones devuelven
CommandResult; la persistencia SQLite (audit trail) la hace este
servicio vía core.persistence.ScheduledRestartStore — paralela a la
fuente de verdad de Windows (schtasks).

Endpoints expuestos a routes/:
- get_uptime() / get_task_status() — read-only, NO requieren governance.
- create_task(...) / delete_task() — mutating, DEBEN llamarse vía
  governance.execute_governed_action (router lo hace).
"""

import logging
from datetime import datetime

from services.command_runner import (
    run_powershell,
    CommandResult,
    CommandStatus,
)
from core.persistence import ScheduledRestartStore

logger = logging.getLogger("cleancpu.scheduled_restart")

TASK_NAME = "CleanCPU_Restart"

# Periodos de gracia válidos (minutos). Validados server-side; cualquier
# otro valor es rechazado.
ALLOWED_GRACE = {1, 5, 15, 30, 60}
ALLOWED_RECURRENCE = {"Once", "Daily", "Weekly", "Monthly"}

# Map de recurrencia a flags de New-ScheduledTaskTrigger.
_TRIGGER_MAP = {
    "Once": "-Once",
    "Daily": "-Daily",
    "Weekly": "-Weekly",
    "Monthly": "-Daily -DaysInterval 30",
}


# ---------------------------------------------------------------------------
# Read-only (NO governance)
# ---------------------------------------------------------------------------


def get_uptime() -> CommandResult:
    """Read-only: tiempo de actividad del equipo via Get-CimInstance."""
    return run_powershell(
        "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; "
        "$span = (Get-Date) - $boot; "
        "[ordered]@{ "
        "  days    = $span.Days; "
        "  hours   = $span.Hours; "
        "  minutes = $span.Minutes; "
        '  boot_time = $boot.ToString("yyyy-MM-dd HH:mm") '
        "} | ConvertTo-Json -Compress",
        timeout=15,
        description="Query system uptime",
    )


def get_task_status() -> CommandResult:
    """Read-only: existencia + estado de la tarea programada."""
    return run_powershell(
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
        description="Check scheduled restart task",
    )


# ---------------------------------------------------------------------------
# Mutating (DEBEN ir por governance.execute_governed_action)
# ---------------------------------------------------------------------------


def create_task(
    date: str = "",
    time: str = "",
    recurrence: str = "Once",
    grace_period: int = 5,
    force: bool = False,
    force_confirmed: bool = False,
    session_id: str = "",
    username: str = "",
) -> CommandResult:
    """Crea o actualiza la tarea programada de reinicio.

    Normal path (force=False): shutdown.exe /r /t <grace_seconds>.
    Forced path (force=True): shutdown.exe /r /f /t 0. Requiere doble
    confirmación: force=True AND force_confirmed=True.

    session_id/username son inyectados por el flujo de governance para
    audit trail (no los pasa el cliente).
    """
    # --- Validaciones de input ---
    if not date or not time:
        return CommandResult(
            status=CommandStatus.ERROR,
            error="Fecha y hora son obligatorios.",
        )

    datetime_str = f"{date} {time}"
    try:
        scheduled_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        if recurrence == "Once" and scheduled_dt < datetime.now():
            return CommandResult(
                status=CommandStatus.ERROR,
                error="No se puede programar en el pasado.",
            )
    except ValueError:
        return CommandResult(
            status=CommandStatus.ERROR,
            error="Formato de fecha/hora no válido.",
        )

    if recurrence not in ALLOWED_RECURRENCE:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f"Recurrencia no válida: {recurrence}. "
            f"Permitidas: {sorted(ALLOWED_RECURRENCE)}.",
        )

    # --- Force path double-lock ---
    if force:
        if not force_confirmed:
            logger.warning(
                "[REJECT] Force restart attempted without force_confirmed flag "
                "for task at %s",
                datetime_str,
            )
            return CommandResult(
                status=CommandStatus.ERROR,
                error=(
                    "Reinicio forzado requiere confirmación explícita "
                    "(force_confirmed=true). Use el formulario de reinicio "
                    "forzado en la interfaz."
                ),
            )
        logger.warning(
            "[FORCE] Forced restart scheduled: %s, recurrence=%s — "
            "machine may be in active use",
            datetime_str,
            recurrence,
        )
        shutdown_args = "/r /f /t 0"
        description_tag = "[FORZADO] Reinicio forzado por CleanCPU"
        effective_grace = 0
    else:
        try:
            grace_period = int(grace_period)
        except (ValueError, TypeError):
            grace_period = 5
        if grace_period not in ALLOWED_GRACE:
            return CommandResult(
                status=CommandStatus.ERROR,
                error=(
                    f"Período de gracia no válido: {grace_period}. "
                    f"Valores permitidos: {sorted(ALLOWED_GRACE)} minutos."
                ),
            )
        grace_seconds = grace_period * 60
        logger.info(
            "[NORMAL] Restart scheduled: %s, grace=%dmin, recurrence=%s",
            datetime_str,
            grace_period,
            recurrence,
        )
        shutdown_args = f"/r /t {grace_seconds}"
        description_tag = (
            f"[NORMAL] Reinicio programado por CleanCPU " f"(aviso {grace_period} min)"
        )
        effective_grace = grace_period

    trigger_flag = _TRIGGER_MAP.get(recurrence, "-Once")

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
        description="Create scheduled restart task",
    )

    success = result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING)

    # Audit trail. Nunca rompe el flujo si la DB falla.
    try:
        ScheduledRestartStore.record_create(
            scheduled_at=datetime_str,
            recurrence=recurrence,
            grace_period=effective_grace,
            force=force,
            success=success,
            error=result.error or "",
            session_id=session_id,
            username=username,
        )
    except Exception as e:
        logger.warning("Audit trail save failed (create): %s", e)

    if success:
        if force:
            msg = (
                f"Reinicio FORZADO programado para {datetime_str} ({recurrence}). "
                "No habrá aviso al usuario — todos los programas se cerrarán."
            )
        else:
            msg = (
                f"Reinicio programado para {datetime_str} ({recurrence}). "
                f"Se mostrará un aviso de {grace_period} min al usuario."
            )
        return CommandResult(status=CommandStatus.SUCCESS, output=msg)

    return CommandResult(
        status=CommandStatus.ERROR,
        error=result.error or "No se pudo crear la tarea programada.",
    )


def delete_task(
    session_id: str = "",
    username: str = "",
) -> CommandResult:
    """Borra la tarea programada de reinicio."""
    result = run_powershell(
        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false",
        requires_admin=True,
        timeout=15,
        description="Delete scheduled restart task",
    )

    success = result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING)

    try:
        ScheduledRestartStore.record_delete(
            success=success,
            error=result.error or "",
            session_id=session_id,
            username=username,
        )
    except Exception as e:
        logger.warning("Audit trail save failed (delete): %s", e)

    if success:
        logger.info("[DELETE] Scheduled restart task deleted.")
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output="Tarea de reinicio eliminada.",
        )

    return CommandResult(
        status=CommandStatus.ERROR,
        error=result.error or "No se pudo eliminar la tarea.",
    )
