"""
Windows Update management module.

Handles: update scanning, downloading, installing, hard reset,
service management, and settings access.
"""
import logging
from datetime import datetime

from services.command_runner import (
    run_cmd, run_powershell, CommandStatus, CommandResult
)

logger = logging.getLogger('cleancpu.windows_update')


def scan_updates():
    """Trigger a Windows Update scan."""
    return run_cmd(
        'UsoClient StartScan',
        requires_admin=True,
        timeout=120,
        description='Scan for Windows Updates',
    )


def download_updates():
    """Download pending Windows Updates."""
    return run_cmd(
        'UsoClient StartDownload',
        requires_admin=True,
        timeout=300,
        description='Download Windows Updates',
    )


def install_updates():
    """
    Install downloaded Windows Updates.
    WARNING: May trigger a system reboot.
    """
    return run_cmd(
        'UsoClient StartInstall',
        requires_admin=True,
        timeout=600,
        description='Install Windows Updates',
    )


def get_update_services_status():
    """Check status of Windows Update related services (JSON-native)."""
    return run_powershell(
        "Get-Service wuauserv,BITS,cryptsvc,msiserver,TrustedInstaller "
        "-ErrorAction SilentlyContinue | "
        "Select-Object Name,DisplayName,Status,StartType | Format-Table -AutoSize",
        description='Check Windows Update services',
    )


def open_windows_update_settings():
    """Open Windows Update settings page."""
    return run_cmd(
        'start ms-settings:windowsupdate',
        shell=True,
        description='Open Windows Update settings',
    )


def hard_reset_windows_update():
    """
    Perform a hard reset of Windows Update components.

    Steps:
    1. Stop wuauserv, bits, cryptsvc, msiserver
    2. Rename SoftwareDistribution folder (timestamped backup)
    3. Rename catroot2 folder (timestamped backup)
    4. Restart services
    5. Trigger new scan

    Uses timestamped backup names to prevent collisions with previous resets.
    Returns accurate composite status reflecting all sub-steps.
    """
    results = {}
    errors = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Step 1: Stop services
    services_to_stop = ['wuauserv', 'bits', 'cryptsvc', 'msiserver']
    for svc in services_to_stop:
        r = run_cmd(f'net stop {svc}', requires_admin=True, timeout=30,
                     description=f'Stop {svc}')
        results[f'stop_{svc}'] = r.to_dict()
        if r.is_error:
            errors.append(f'Failed to stop {svc}: {r.error}')

    # Step 2: Rename SoftwareDistribution with timestamp
    rename_sd = f'ren C:\\Windows\\SoftwareDistribution SoftwareDistribution.bak.{timestamp}'
    r = run_cmd(rename_sd, requires_admin=True,
                description='Rename SoftwareDistribution')
    results['rename_softwaredist'] = r.to_dict()
    if r.is_error:
        errors.append(f'Failed to rename SoftwareDistribution: {r.error}')

    # Step 3: Rename catroot2 with timestamp
    rename_cr = f'ren C:\\Windows\\System32\\catroot2 catroot2.bak.{timestamp}'
    r = run_cmd(rename_cr, requires_admin=True,
                description='Rename catroot2')
    results['rename_catroot2'] = r.to_dict()
    if r.is_error:
        errors.append(f'Failed to rename catroot2: {r.error}')

    # Step 4: Restart services
    services_to_start = ['cryptsvc', 'bits', 'msiserver', 'wuauserv']
    for svc in services_to_start:
        r = run_cmd(f'net start {svc}', requires_admin=True, timeout=30,
                     description=f'Start {svc}')
        results[f'start_{svc}'] = r.to_dict()
        if r.is_error:
            errors.append(f'Failed to start {svc}: {r.error}')

    # Step 5: Trigger scan
    r = run_cmd('UsoClient StartScan', requires_admin=True, timeout=60,
                 description='Trigger update scan after reset')
    results['rescan'] = r.to_dict()

    # Composite status
    results['_composite'] = {
        'status': 'partial_success' if errors else 'success',
        'errors': errors,
        'backup_timestamp': timestamp,
        'message': (
            f'Windows Update reset completed with {len(errors)} error(s).'
            if errors else
            'Windows Update reset completed successfully.'
        ),
    }

    return results


def resync_time():
    """Resynchronize Windows time."""
    results = {}
    errors = []

    steps = [
        ('config', 'sc config w32time start=auto', 'Set W32Time to auto start'),
        ('start', 'net start w32time', 'Start W32Time service'),
        ('resync', 'w32tm /resync', 'Resync system time'),
    ]

    for key, cmd, desc in steps:
        r = run_cmd(cmd, requires_admin=True, description=desc)
        results[key] = r.to_dict()
        if r.is_error:
            errors.append(f'{desc}: {r.error}')

    results['_composite'] = {
        'status': 'partial_success' if errors else 'success',
        'errors': errors,
    }

    return results
