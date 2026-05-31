"""
Driver diagnostics module.

Handles: driver enumeration, problem detection, driver info, backup.
NOTE: Driver deletion (pnputil /delete-driver) is NOT automated
due to extreme risk of bricking devices.
NOTE: Driver auto-update is NOT implemented (snake-oil risk). Use
Windows Update or vendor-supplied updaters (Lenovo Update step in
the maintenance flow).
"""

import datetime
import logging
import os
import re

from services.command_runner import (
    CommandResult,
    CommandStatus,
    run_cmd,
    run_powershell,
)

logger = logging.getLogger("maintenance.drivers")


def enum_drivers():
    """Enumerate all installed third-party drivers."""
    return run_cmd(
        "pnputil /enum-drivers",
        description="Enumerate installed drivers",
    )


def enum_problem_devices():
    """Find devices with problems."""
    return run_cmd(
        "pnputil /enum-devices /problem",
        description="Find devices with problems",
    )


def get_driver_details():
    """Get detailed driver information via PowerShell."""
    return run_powershell(
        "Get-CimInstance Win32_PnPSignedDriver | "
        'Where-Object {$_.DriverProviderName -ne "Microsoft"} | '
        "Select-Object DeviceName,DriverVersion,DriverProviderName,DriverDate,IsSigned | "
        "Sort-Object DeviceName | Format-Table -AutoSize",
        description="Get third-party driver details",
    )


def get_display_drivers():
    """Get display/GPU driver information specifically."""
    return run_powershell(
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,DriverVersion,DriverDate,Status,VideoProcessor,AdapterRAM | "
        "Format-List",
        description="Get display driver info",
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
        description="Find driver errors in event log",
    )


def get_driver_overview():
    """Get a complete driver overview."""
    results = {}
    results["all_drivers"] = enum_drivers().to_dict()
    results["problem_devices"] = enum_problem_devices().to_dict()
    results["third_party"] = get_driver_details().to_dict()
    results["display_drivers"] = get_display_drivers().to_dict()
    results["driver_errors"] = get_driver_errors().to_dict()
    return results


# Restrict backup destinations: only paths under fixed local drives
# (no UNC, no removable, no network mounts) — empresarial safety.
_VALID_DEST_RE = re.compile(r"^[A-Za-z]:\\(?!\\)")


def _resolve_backup_dest(dest_path: str) -> str:
    """Validate and normalize the backup destination path.

    Raises ValueError if the path is unsafe (UNC, missing drive letter,
    relative, contains parent-dir traversal).
    """
    if not isinstance(dest_path, str) or not dest_path.strip():
        raise ValueError("dest_path is required.")
    p = dest_path.strip().replace("/", "\\")
    if ".." in p.split("\\"):
        raise ValueError("Parent-dir traversal not allowed in dest_path.")
    if not _VALID_DEST_RE.match(p):
        raise ValueError(
            "dest_path must be an absolute local path like 'C:\\backup\\drivers'."
        )
    return p


def backup_drivers(dest_path: str) -> CommandResult:
    """Export all installed third-party drivers via `pnputil /export-driver *`.

    Creates `<dest_path>\\drivers_backup_<YYYYMMDD_HHMMSS>` and exports there,
    so repeated runs don't overwrite. Requires admin privileges.

    Returns success with details:
      - target_dir: the timestamped output directory
      - exported_count: parsed driver count (best-effort) if pnputil reports it
    """
    try:
        base = _resolve_backup_dest(dest_path)
    except ValueError as e:
        return CommandResult(
            status=CommandStatus.ERROR,
            output=str(e),
            error=str(e),
        )

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = os.path.join(base, f"drivers_backup_{stamp}")

    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        return CommandResult(
            status=CommandStatus.ERROR,
            output=f"Cannot create target dir: {e}",
            error=str(e),
        )

    quoted = '"' + target_dir + '"'
    result = run_cmd(
        f"pnputil /export-driver * {quoted}",
        timeout=600,
        requires_admin=True,
        description="Export third-party drivers",
    )

    exported = None
    if result.output:
        m = re.search(r"(\d+)\s+driver", result.output, re.IGNORECASE)
        if m:
            try:
                exported = int(m.group(1))
            except ValueError:
                exported = None

    details = dict(result.details or {})
    details.update(
        {
            "target_dir": target_dir,
            "exported_count": exported,
        }
    )
    return CommandResult(
        status=result.status,
        output=(
            f"Drivers exported to {target_dir}"
            + (f" ({exported} drivers reported)" if exported is not None else "")
        ),
        error=result.error,
        return_code=result.return_code,
        details=details,
    )
