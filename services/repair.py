"""
OS health and repair module.

Handles: SFC, DISM (CheckHealth/ScanHealth/RestoreHealth), ComponentCleanup,
CHKDSK, WinSAT, memory diagnostics.
"""
import logging

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.repair')


def run_sfc_scan():
    """
    Run System File Checker (sfc /scannow).
    Safe: repairs corrupted system files from local cache.
    """
    return run_cmd(
        'sfc /scannow',
        requires_admin=True,
        timeout=900,
        description='System File Checker (SFC)',
    )


def dism_check_health():
    """
    DISM CheckHealth - Quick integrity check.
    Safe: read-only, fast.
    """
    return run_cmd(
        'DISM /Online /Cleanup-Image /CheckHealth',
        requires_admin=True,
        timeout=120,
        description='DISM CheckHealth',
    )


def dism_scan_health():
    """
    DISM ScanHealth - Deeper integrity scan.
    Safe: read-only but slower.
    """
    return run_cmd(
        'DISM /Online /Cleanup-Image /ScanHealth',
        requires_admin=True,
        timeout=600,
        description='DISM ScanHealth',
    )


def dism_restore_health():
    """
    DISM RestoreHealth - Repair component store.
    May download files from Windows Update.
    """
    return run_cmd(
        'DISM /Online /Cleanup-Image /RestoreHealth',
        requires_admin=True,
        timeout=1800,
        description='DISM RestoreHealth',
    )


def dism_component_cleanup():
    """Remove superseded Windows components."""
    return run_cmd(
        'DISM /Online /Cleanup-Image /StartComponentCleanup',
        requires_admin=True,
        timeout=600,
        description='DISM StartComponentCleanup',
    )


def chkdsk_scan_online():
    """
    CHKDSK online scan (non-destructive, no reboot required).
    Safe alternative to chkdsk /f /r.
    """
    return run_cmd(
        'chkdsk C: /scan',
        requires_admin=True,
        timeout=600,
        description='CHKDSK online scan',
    )


def chkdsk_schedule_full():
    """
    Schedule a full CHKDSK on next reboot.
    WARNING: Requires reboot, can take a long time.
    Does NOT force reboot - just schedules the check.
    """
    return run_cmd(
        'chkdsk C: /f /r /x',
        requires_admin=True,
        timeout=30,
        description='Schedule full CHKDSK (next reboot)',
    )


def winsat_disk():
    """Run Windows System Assessment Tool for disk performance."""
    return run_cmd(
        'winsat disk -drive c',
        requires_admin=True,
        timeout=120,
        description='WinSAT disk benchmark',
    )


def schedule_memory_diagnostic():
    """
    Open Windows Memory Diagnostic tool.
    This schedules a memory test on next reboot.
    """
    return run_cmd(
        'mdsched.exe',
        requires_admin=True,
        timeout=10,
        description='Schedule memory diagnostic',
    )


def run_repair_sequence():
    """
    Run the full repair sequence in proper order:
    1. SFC /scannow
    2. DISM /CheckHealth
    3. DISM /ScanHealth
    4. DISM /RestoreHealth
    5. StartComponentCleanup

    Returns results for each step.
    """
    results = {}

    steps = [
        ('sfc', 'SFC /scannow', run_sfc_scan),
        ('dism_check', 'DISM CheckHealth', dism_check_health),
        ('dism_scan', 'DISM ScanHealth', dism_scan_health),
        ('dism_restore', 'DISM RestoreHealth', dism_restore_health),
        ('component_cleanup', 'DISM StartComponentCleanup', dism_component_cleanup),
    ]

    for key, name, func in steps:
        logger.info(f"Repair sequence - starting: {name}")
        result = func()
        results[key] = result.to_dict()
        logger.info(f"Repair sequence - completed: {name} ({result.status})")

        # If a step fails critically, log but continue
        if result.status == CommandStatus.ERROR:
            logger.warning(f"Repair step {name} failed, continuing sequence...")

    return results
