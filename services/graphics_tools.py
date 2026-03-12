"""
Graphics and display diagnostics module.

Handles: display/DWM events, Intel graphics driver inspection,
Panel Self Refresh guidance.
"""
import logging

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.graphics')


def get_display_events(max_events=30):
    """Get display and DWM related events from Windows Event Log."""
    return run_powershell(
        f'Get-WinEvent -FilterHashtable @{{LogName="System"; '
        f'ProviderName="*dwm*","*display*","*gpu*","*video*"}} '
        f'-MaxEvents {max_events} -ErrorAction SilentlyContinue | '
        f'Select-Object TimeCreated,Id,LevelDisplayName,Message | '
        f'Format-List',
        requires_admin=True,
        timeout=30,
        description='Get display/DWM events',
    )


def get_gpu_drivers():
    """List installed display/GPU drivers."""
    return run_powershell(
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,DriverVersion,DriverDate,Status,AdapterRAM | "
        "Format-List",
        description='Get GPU driver info',
    )


def get_intel_graphics_drivers():
    """Specifically list Intel graphics related drivers."""
    return run_cmd(
        'pnputil /enum-drivers /class Display',
        description='Enumerate display drivers',
    )


def check_panel_self_refresh():
    """
    Check for Intel Panel Self Refresh issues.
    This is a diagnostic check - actual PSR disable requires Intel Graphics Command Center
    or registry modification (advanced).
    """
    result = run_powershell(
        "Get-WinEvent -FilterHashtable @{LogName='System'} -MaxEvents 100 "
        "-ErrorAction SilentlyContinue | "
        "Where-Object {$_.Message -match 'display|panel|refresh|flicker'} | "
        "Select-Object -First 10 TimeCreated,Id,Message | Format-List",
        requires_admin=True,
        timeout=30,
        description='Check for Panel Self Refresh related events',
    )

    guidance = (
        "If display flickering is detected:\n"
        "1. Open Intel Graphics Command Center\n"
        "2. Go to System > Power\n"
        "3. Disable 'Panel Self Refresh'\n"
        "4. If Intel GCC is not installed, this may require registry changes\n"
        "   (advanced - not automated for safety)"
    )

    if result.is_success:
        result.details['guidance'] = guidance

    return result


def get_display_diagnostics():
    """Run all display-related diagnostics."""
    results = {}
    results['display_events'] = get_display_events().to_dict()
    results['gpu_drivers'] = get_gpu_drivers().to_dict()
    results['intel_drivers'] = get_intel_graphics_drivers().to_dict()
    results['psr_check'] = check_panel_self_refresh().to_dict()
    return results
