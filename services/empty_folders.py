"""Detect and remove empty folders under user-writable roots.

Safe defaults:
  - Only scans paths under the current user profile by default.
  - Excludes system / AppData paths where empty folders may be intentional
    (caches that fill at runtime, app state directories).
  - Deletes one folder at a time, re-verifying emptiness server-side before
    each removal, via Recycle Bin so the user can recover.

Empty == zero files AND zero subdirectories (using -Force so hidden items
count).
"""

import json
import logging

from services.command_runner import (
    CommandResult,
    CommandStatus,
    run_powershell,
)

logger = logging.getLogger("cleancpu.empty_folders")


# Tokens that, if present in a path (case-insensitive), exclude that path
# from scan and from deletion. Hard-coded for safety.
PROTECTED_TOKENS = (
    "\\appdata\\",
    "\\microsoft\\",
    "\\windows\\",
    "\\program files",
    "\\programdata\\",
    "\\system32\\",
    "\\syswow64\\",
    "\\$recycle.bin\\",
    "\\onedrive\\",
    "\\.git\\",
    "\\.svn\\",
    "\\node_modules\\",
)


def _is_protected(path: str) -> bool:
    if not path:
        return True
    p = path.lower().replace("/", "\\") + "\\"
    return any(tok in p for tok in PROTECTED_TOKENS)


def scan_empty_folders(root_path: str = "", max_depth: int = 8) -> CommandResult:
    """Scan for empty folders under `root_path`.

    If `root_path` is empty / None, defaults to the user profile.
    Protected system paths are always excluded.
    """
    if not root_path:
        root_path = r"$env:USERPROFILE"
        root_repr = root_path
    else:
        if _is_protected(root_path):
            return CommandResult(
                status=CommandStatus.ERROR,
                output=f"Refused to scan protected path: {root_path}",
            )
        root_repr = "'" + root_path.replace("'", "''") + "'"

    try:
        depth = int(max_depth)
    except (TypeError, ValueError):
        depth = 8
    depth = max(1, min(depth, 16))

    ps = (
        '$ErrorActionPreference = "SilentlyContinue";'
        f"$root = {root_repr};"
        "if (-not (Test-Path -LiteralPath $root)) {"
        "  [pscustomobject]@{ error='Root not found'; root=$root } | ConvertTo-Json -Compress;"
        "  return;"
        "}"
        f"$maxDepth = {depth};"
        "$results = @();"
        "Get-ChildItem -LiteralPath $root -Directory -Recurse -Depth $maxDepth -Force "
        "  -ErrorAction SilentlyContinue | ForEach-Object {"
        "    $d = $_;"
        "    $items = Get-ChildItem -LiteralPath $d.FullName -Force "
        "      -ErrorAction SilentlyContinue;"
        "    if ($items -eq $null -or @($items).Count -eq 0) {"
        "      $results += [pscustomobject]@{"
        "        path = $d.FullName;"
        "        name = $d.Name;"
        "        parent = $d.Parent.FullName;"
        "      };"
        "    }"
        "};"
        "[pscustomobject]@{"
        "  root  = $root;"
        "  count = $results.Count;"
        "  items = @($results);"
        "} | ConvertTo-Json -Compress -Depth 4"
    )

    result = run_powershell(
        ps,
        timeout=300,
        description=f"Scan empty folders under {root_path}",
    )
    if result.status != CommandStatus.SUCCESS:
        return result

    try:
        raw = (result.output or "").strip()
        data = json.loads(raw) if raw else {"items": [], "count": 0}
        if data.get("error"):
            return CommandResult(
                status=CommandStatus.NOT_APPLICABLE,
                output=data["error"],
                details=data,
            )
        items = data.get("items")
        if isinstance(items, dict):
            items = [items]
        elif items is None:
            items = []
        # Apply protected filter server-side too (belt + suspenders).
        items = [it for it in items if not _is_protected(it.get("path", ""))]
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Found {len(items)} empty folder(s).",
            details={
                "root": data.get("root"),
                "count": len(items),
                "items": items,
            },
        )
    except (json.JSONDecodeError, ValueError) as e:
        return CommandResult(
            status=CommandStatus.ERROR,
            output=f"Parse error: {e}",
            error=str(e),
        )


def delete_empty_folders(paths) -> CommandResult:
    """Delete listed folders, one by one, after re-verifying each is empty.

    Sends to Recycle Bin (reversible). Protected tokens reject upfront.
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

    safe_paths = [
        p for p in paths if isinstance(p, str) and p.strip() and not _is_protected(p)
    ]
    if not safe_paths:
        return CommandResult(
            status=CommandStatus.ERROR,
            output="No valid paths after protected-tokens filter.",
        )

    ps_array = (
        "@(" + ",".join("'" + p.replace("'", "''") + "'" for p in safe_paths) + ")"
    )
    ps = (
        "Add-Type -AssemblyName Microsoft.VisualBasic;"
        '$ErrorActionPreference = "SilentlyContinue";'
        "$results = @();"
        f"$inputs = {ps_array};"
        "foreach ($p in $inputs) {"
        "  if (-not (Test-Path -LiteralPath $p)) {"
        "    $results += [pscustomobject]@{path=$p;status='not_found'}; continue;"
        "  }"
        "  $items = Get-ChildItem -LiteralPath $p -Force -ErrorAction SilentlyContinue;"
        "  if ($items -ne $null -and @($items).Count -gt 0) {"
        "    $results += [pscustomobject]@{path=$p;status='skipped_not_empty'};"
        "    continue;"
        "  }"
        "  try {"
        "    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory("
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
        timeout=300,
        description="Delete empty folders",
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
            output=f"Deleted {deleted} of {len(safe_paths)} folder(s).",
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
