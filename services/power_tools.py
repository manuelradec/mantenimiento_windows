"""
Power and performance management module.

Handles: power plans, active scheme, battery report, hibernation,
processor power settings.
"""
import logging

from services.command_runner import (
    run_cmd, run_powershell, CommandStatus, CommandResult
)

logger = logging.getLogger('maintenance.power')


def get_active_power_plan():
    """Get the currently active power plan."""
    return run_cmd(
        'powercfg /GETACTIVESCHEME',
        description='Get active power plan',
    )


def get_power_plan_details():
    """Get detailed power plan settings."""
    return run_cmd(
        'powercfg /Q',
        description='Get power plan details',
    )


def list_power_plans():
    """List all available power plans."""
    return run_cmd(
        'powercfg /LIST',
        description='List power plans',
    )


def set_high_performance():
    """Switch to High Performance power plan."""
    return run_cmd(
        'powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
        requires_admin=True,
        description='Set High Performance power plan',
    )


def set_balanced():
    """Switch to Balanced power plan."""
    return run_cmd(
        'powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
        requires_admin=True,
        description='Set Balanced power plan',
    )


def _has_battery() -> bool:
    """
    Detect battery presence via WMI so ``powercfg /batteryreport`` is never
    invoked on desktops. Returns True only when a Win32_Battery instance
    is exposed by CIM; on error falls back to False so we skip cleanly
    rather than letting powercfg emit its confusing desktop error.
    """
    probe = run_powershell(
        "$b = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue; "
        "if ($b) { 'yes' } else { 'no' }",
        timeout=10,
        description='Detect battery presence',
    )
    if not probe.is_success:
        return False
    return (probe.output or '').strip().lower().startswith('yes')


def get_battery_report():
    """Generate a battery report (laptops only)."""
    import os
    import sys
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    if not _has_battery():
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='Este equipo no tiene bateria (probablemente un desktop). '
                   'Se omite el reporte de bateria.',
        )

    report_path = os.path.join(
        os.environ.get('PROGRAMDATA', 'C:\\ProgramData'),
        'CleanCPU', 'reports', 'battery-report.html'
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    result = run_cmd(
        f'powercfg /batteryreport /output "{report_path}"',
        description='Generate battery report',
    )
    if result.is_success:
        result.details['report_path'] = report_path
    return result


def disable_hibernation():
    """
    Disable hibernation and delete hiberfil.sys.
    Frees disk space equal to RAM size.
    WARNING: Removes ability to hibernate.
    """
    return run_cmd(
        'powercfg -h off',
        requires_admin=True,
        description='Disable hibernation',
    )


def enable_hibernation():
    """Re-enable hibernation."""
    return run_cmd(
        'powercfg -h on',
        requires_admin=True,
        description='Enable hibernation',
    )


def get_processor_power_info():
    """Get current processor power management counters."""
    result = run_powershell(
        "Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 2 -MaxSamples 3",
        timeout=15,
        description='Get processor power counters',
    )
    # rc=1 means some counters may be unavailable on this machine — treat as non-critical
    if result.return_code == 1 and result.output:
        result.status = CommandStatus.SUCCESS
        result.output += (
            '\n\nNota: Algunos contadores de rendimiento pueden no estar '
            'disponibles en este equipo.'
        )
    return result
