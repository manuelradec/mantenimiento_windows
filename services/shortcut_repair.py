"""Detect and repair broken .lnk shortcuts whose target no longer exists.

Scans typical locations for current user and all-users profiles. Broken
shortcuts are reported with their target so the technician decides what to
delete. Deletion moves files to the Recycle Bin via
Microsoft.VisualBasic.FileIO so it is reversible by the end user.

Locations scanned:
  - Desktop (user + common)
  - Start Menu (user + common)
  - Programs (user + common)

Why this matters: legacy shortcuts to uninstalled or moved apps clutter the
Start Menu and confuse end users. Removing them is high-value, low-risk.
"""

import json
import logging

from services.command_runner import (
    CommandResult,
    CommandStatus,
    run_powershell,
)

logger = logging.getLogger("cleancpu.shortcut_repair")


_PS_SCAN = r"""
$ErrorActionPreference = "SilentlyContinue"
$locations = @(
    @{ name = "user_desktop";     path = [Environment]::GetFolderPath("Desktop") },
    @{ name = "common_desktop";   path = [Environment]::GetFolderPath("CommonDesktopDirectory") },
    @{ name = "user_startmenu";   path = [Environment]::GetFolderPath("StartMenu") },
    @{ name = "common_startmenu"; path = [Environment]::GetFolderPath("CommonStartMenu") },
    @{ name = "user_programs";    path = [Environment]::GetFolderPath("Programs") },
    @{ name = "common_programs";  path = [Environment]::GetFolderPath("CommonPrograms") }
)
$shell = New-Object -ComObject WScript.Shell
$results = @()
foreach ($loc in $locations) {
    if (-not (Test-Path -LiteralPath $loc.path)) { continue }
    $files = Get-ChildItem -Path $loc.path -Filter "*.lnk" -File -Recurse -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        try {
            $sc = $shell.CreateShortcut($f.FullName)
            $target = $sc.TargetPath
            if ([string]::IsNullOrWhiteSpace($target)) { continue }
            if (Test-Path -LiteralPath $target) { continue }
            $results += [pscustomobject]@{
                location  = $loc.name
                lnk_path  = $f.FullName
                lnk_name  = $f.Name
                target    = $target
                arguments = $sc.Arguments
            }
        } catch { }
    }
}
[pscustomobject]@{
    broken_count = $results.Count
    broken       = @($results)
} | ConvertTo-Json -Compress -Depth 4
"""


def scan_broken_shortcuts():
    """Scan typical locations for .lnk shortcuts whose target is missing.

    Returns CommandResult with details:
      - broken_count: int
      - broken: list of {location, lnk_path, lnk_name, target, arguments}
    """
    result = run_powershell(
        _PS_SCAN,
        timeout=120,
        description="Scan broken shortcuts",
    )
    if result.status != CommandStatus.SUCCESS:
        return result
    try:
        raw = (result.output or "").strip()
        data = json.loads(raw) if raw else {"broken_count": 0, "broken": []}
        broken = data.get("broken")
        if isinstance(broken, dict):
            broken = [broken]
        elif broken is None:
            broken = []
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Found {len(broken)} broken shortcut(s).",
            details={
                "broken_count": len(broken),
                "broken": broken,
            },
        )
    except (json.JSONDecodeError, ValueError) as e:
        return CommandResult(
            status=CommandStatus.ERROR,
            output=f"Parse error: {e}",
            error=str(e),
        )


def delete_broken_shortcuts(paths):
    """Delete listed .lnk paths via Recycle Bin.

    Re-validates each item server-side: must end in .lnk and its resolved
    target must NOT exist. Skips otherwise (status: skipped_target_exists,
    skipped_empty_target, not_found, error).
    """
    if not isinstance(paths, list) or not paths:
        return CommandResult(
            status=CommandStatus.ERROR,
            output="No paths provided.",
        )
    if len(paths) > 500:
        return CommandResult(
            status=CommandStatus.ERROR,
            output="Too many paths in single batch (max 500).",
        )
    safe_paths = [p for p in paths if isinstance(p, str) and p.lower().endswith(".lnk")]
    if not safe_paths:
        return CommandResult(
            status=CommandStatus.ERROR,
            output="No valid .lnk paths in input.",
        )
    ps_array = (
        "@(" + ",".join("'" + p.replace("'", "''") + "'" for p in safe_paths) + ")"
    )
    ps = (
        "Add-Type -AssemblyName Microsoft.VisualBasic;"
        "$shell = New-Object -ComObject WScript.Shell;"
        "$results = @();"
        f"$inputs = {ps_array};"
        "foreach ($p in $inputs) {"
        "  if (-not (Test-Path -LiteralPath $p)) {"
        "    $results += [pscustomobject]@{path=$p;status='not_found'}; continue;"
        "  }"
        "  try {"
        "    $sc = $shell.CreateShortcut($p);"
        "    $t = $sc.TargetPath;"
        "    if ([string]::IsNullOrWhiteSpace($t)) {"
        "      $results += [pscustomobject]@{path=$p;status='skipped_empty_target'}; continue;"
        "    }"
        "    if (Test-Path -LiteralPath $t) {"
        "      $results += [pscustomobject]@{path=$p;status='skipped_target_exists'}; continue;"
        "    }"
        "    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
        "      $p,"
        "      [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,"
        "      [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin);"
        "    $results += [pscustomobject]@{path=$p;status='deleted'};"
        "  } catch { $results += [pscustomobject]@{path=$p;status='error';error=$_.Exception.Message}; }"
        "}"
        "[pscustomobject]@{results=@($results);count=$results.Count} "
        "| ConvertTo-Json -Compress -Depth 4"
    )
    result = run_powershell(
        ps,
        timeout=120,
        description="Delete broken shortcuts",
    )
    if result.status != CommandStatus.SUCCESS:
        return result
    try:
        raw = (result.output or "").strip()
        data = json.loads(raw) if raw else {"results": []}
        results = data.get("results") or []
        if isinstance(results, dict):
            results = [results]
        deleted = sum(1 for r in results if r.get("status") == "deleted")
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Deleted {deleted} of {len(safe_paths)} shortcut(s).",
            details={
                "results": results,
                "deleted_count": deleted,
                "input_count": len(safe_paths),
            },
        )
    except (json.JSONDecodeError, ValueError) as e:
        return CommandResult(
            status=CommandStatus.ERROR,
            output=f"Parse error: {e}",
            error=str(e),
        )
