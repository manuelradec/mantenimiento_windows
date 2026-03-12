"""
Windows Update management module.

Handles: update scanning, downloading, installing, hard reset,
service management, and settings access.
"""
import logging

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.windows_update')


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
    """Check status of Windows Update related services."""
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
    This is the nuclear option for when Windows Update is broken.

    Steps:
    1. Stop wuauserv, bits, cryptsvc, msiserver
    2. Rename SoftwareDistribution folder
    3. Rename catroot2 folder
    4. Restart services
    5. Trigger new scan

    WARNING: Only use when Windows Update is broken and other methods failed.
    """
    results = {}

    # Step 1: Stop services
    services_to_stop = ['wuauserv', 'bits', 'cryptsvc', 'msiserver']
    for svc in services_to_stop:
        r = run_cmd(f'net stop {svc}', requires_admin=True, timeout=30,
                     description=f'Stop {svc}')
        results[f'stop_{svc}'] = r.to_dict()

    # Step 2: Rename SoftwareDistribution
    r = run_cmd(
        'ren C:\\Windows\\SoftwareDistribution SoftwareDistribution.bak',
        requires_admin=True,
        description='Rename SoftwareDistribution',
    )
    results['rename_softwaredist'] = r.to_dict()

    # Step 3: Rename catroot2
    r = run_cmd(
        'ren C:\\Windows\\System32\\catroot2 catroot2.bak',
        requires_admin=True,
        description='Rename catroot2',
    )
    results['rename_catroot2'] = r.to_dict()

    # Step 4: Restart services
    services_to_start = ['cryptsvc', 'bits', 'msiserver', 'wuauserv']
    for svc in services_to_start:
        r = run_cmd(f'net start {svc}', requires_admin=True, timeout=30,
                     description=f'Start {svc}')
        results[f'start_{svc}'] = r.to_dict()

    # Step 5: Trigger scan
    r = run_cmd('UsoClient StartScan', requires_admin=True, timeout=60,
                 description='Trigger update scan after reset')
    results['rescan'] = r.to_dict()

    return results


def resync_time():
    """Resynchronize Windows time."""
    results = {}
    results['config'] = run_cmd(
        'sc config w32time start=auto',
        requires_admin=True,
        description='Set W32Time to auto start',
    ).to_dict()
    results['start'] = run_cmd(
        'net start w32time',
        requires_admin=True,
        description='Start W32Time service',
    ).to_dict()
    results['resync'] = run_cmd(
        'w32tm /resync',
        requires_admin=True,
        description='Resync system time',
    ).to_dict()
    return results
