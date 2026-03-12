"""
Driver diagnostics module.

Handles: driver enumeration, problem detection, driver info.
NOTE: Driver deletion (pnputil /delete-driver) is NOT automated
due to extreme risk of bricking devices.
"""
import logging

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.drivers')


def enum_drivers():
    """Enumerate all installed third-party drivers."""
    return run_cmd(
        'pnputil /enum-drivers',
        description='Enumerate installed drivers',
    )


def enum_problem_devices():
    """Find devices with problems."""
    return run_cmd(
        'pnputil /enum-devices /problem',
        description='Find devices with problems',
    )


def get_driver_details():
    """Get detailed driver information via PowerShell."""
    return run_powershell(
        'Get-CimInstance Win32_PnPSignedDriver | '
        'Where-Object {$_.DriverProviderName -ne "Microsoft"} | '
        'Select-Object DeviceName,DriverVersion,DriverProviderName,DriverDate,IsSigned | '
        'Sort-Object DeviceName | Format-Table -AutoSize',
        description='Get third-party driver details',
    )


def get_display_drivers():
    """Get display/GPU driver information specifically."""
    return run_powershell(
        'Get-CimInstance Win32_VideoController | '
        'Select-Object Name,DriverVersion,DriverDate,Status,VideoProcessor,AdapterRAM | '
        'Format-List',
        description='Get display driver info',
    )


def get_driver_errors():
    """Find drivers with errors in the event log."""
    return run_powershell(
        "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2,3} "
        "-MaxEvents 50 -ErrorAction SilentlyContinue | "
        "Where-Object {$_.Message -match 'driver'} | "
        "Select-Object -First 15 TimeCreated,Id,LevelDisplayName,Message | "
        "Format-List",
        requires_admin=True,
        timeout=30,
        description='Find driver errors in event log',
    )


def get_driver_overview():
    """Get a complete driver overview."""
    results = {}
    results['all_drivers'] = enum_drivers().to_dict()
    results['problem_devices'] = enum_problem_devices().to_dict()
    results['third_party'] = get_driver_details().to_dict()
    results['display_drivers'] = get_display_drivers().to_dict()
    results['driver_errors'] = get_driver_errors().to_dict()
    return results
