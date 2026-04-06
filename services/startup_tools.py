"""
Startup Application Management.

Detects startup items from:
  - HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run  (all-users registry)
  - HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run  (per-user registry)
  - User Startup folder   (%APPDATA%\\...\\Startup)
  - Common Startup folder (%ProgramData%\\...\\Startup)

Enabled/disabled state for registry items is read from the Windows-native
StartupApproved key (same mechanism used by Task Manager and Windows Settings).

Manageable sources (can be toggled):
    registry_hklm  — HKLM Run key value (requires admin for write)
    registry_hkcu  — HKCU Run key value (current user)
    folder_user    — .lnk in user Startup folder
    folder_common  — .lnk in Common Startup folder (requires admin for write)

Non-manageable sources (shown read-only):
    Any other location reported by Win32_StartupCommand that falls outside the
    four categories above (Task Scheduler entries, GPO-injected items, Store
    apps, etc.).  These are surfaced honestly as read-only with a note.

Limitations stated clearly:
  - Win32_StartupCommand is NOT used here; the service reads registry keys
    and Startup folders directly.  Items injected solely via Task Scheduler or
    GPO that do not appear in Run keys or Startup folders will NOT be listed.
  - 32-bit Run keys on 64-bit Windows
    (HKLM\\SOFTWARE\\Wow6432Node\\...\\Run) are not scanned.
  - HKLM RunOnce / RunServices / RunServicesOnce are not scanned.
"""
import json
import logging
import re

from services.command_runner import run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('cleancpu.startup')

# Sources for which this tool can toggle the enabled/disabled state.
_MANAGEABLE_SOURCES = frozenset({
    'registry_hklm',
    'registry_hkcu',
    'folder_user',
    'folder_common',
})

# Human-readable label for each source type (shown in the UI).
_SOURCE_LABELS = {
    'registry_hklm': 'Registro (equipo)',
    'registry_hkcu': 'Registro (usuario)',
    'folder_user': 'Carpeta inicio (usuario)',
    'folder_common': 'Carpeta inicio (todos)',
}

# PowerShell query: reads Run registry keys and Startup folders.
# ConvertTo-Json is included so run_powershell_json does not append it.
# Disabled registry items are detected via the StartupApproved binary key:
#   first byte 0x02 = enabled, anything else = disabled.
# Disabled folder items are detected by scanning for *.lnk.disabled files.
_QUERY_PS = (
    '$items=[System.Collections.Generic.List[hashtable]]::new(); '

    # ---- HKLM Run -------------------------------------------------------
    '$hklmRun="HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"; '
    '$hklmApp="HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\'
    'Explorer\\StartupApproved\\Run"; '
    'if(Test-Path $hklmRun){'
    '  (Get-ItemProperty $hklmRun).PSObject.Properties|'
    '  Where-Object{$_.Name -notmatch "^PS" -and $_.Name -ne "(default)"}|'
    '  ForEach-Object{'
    '    $en=$true;'
    '    if(Test-Path $hklmApp){'
    '      $v=(Get-ItemProperty -Path $hklmApp -ErrorAction SilentlyContinue)."$($_.Name)";'
    '      if($null -ne $v -and $v.Length -ge 1 -and $v[0] -ne 2){$en=$false}};'
    '    $items.Add(@{'
    '      name=[string]$_.Name;command=[string]$_.Value;'
    '      location="HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run";'
    '      user="All Users";enabled=$en;source="registry_hklm"'
    '    })'
    '  }'
    '}; '

    # ---- HKCU Run -------------------------------------------------------
    '$hkcuRun="HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"; '
    '$hkcuApp="HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\'
    'Explorer\\StartupApproved\\Run"; '
    'if(Test-Path $hkcuRun){'
    '  (Get-ItemProperty $hkcuRun).PSObject.Properties|'
    '  Where-Object{$_.Name -notmatch "^PS" -and $_.Name -ne "(default)"}|'
    '  ForEach-Object{'
    '    $en=$true;'
    '    if(Test-Path $hkcuApp){'
    '      $v=(Get-ItemProperty -Path $hkcuApp -ErrorAction SilentlyContinue)."$($_.Name)";'
    '      if($null -ne $v -and $v.Length -ge 1 -and $v[0] -ne 2){$en=$false}};'
    '    $items.Add(@{'
    '      name=[string]$_.Name;command=[string]$_.Value;'
    '      location="HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run";'
    '      user=$env:USERNAME;enabled=$en;source="registry_hkcu"'
    '    })'
    '  }'
    '}; '

    # ---- Startup folders ------------------------------------------------
    '$uSt=[Environment]::GetFolderPath("Startup"); '
    '$cSt=[Environment]::GetFolderPath("CommonStartup"); '
    'foreach($sf in @('
    '  @{path=$uSt;user=$env:USERNAME;src="folder_user"}'
    '  @{path=$cSt;user="All Users";src="folder_common"}'
    ')){'
    '  if(-not $sf.path -or -not (Test-Path $sf.path)){continue}; '
    '  Get-ChildItem -Path $sf.path -Filter "*.lnk" -File -EA SilentlyContinue|'
    '  ForEach-Object{$items.Add(@{'
    '    name=$_.BaseName;command=$_.FullName;'
    '    location=$sf.path;user=$sf.user;enabled=$true;source=$sf.src'
    '  })}; '
    '  Get-ChildItem -Path $sf.path -Filter "*.lnk.disabled" -File -EA SilentlyContinue|'
    '  ForEach-Object{$items.Add(@{'
    '    name=($_.Name -replace "\\.lnk\\.disabled$","");command=$_.FullName;'
    '    location=$sf.path;user=$sf.user;enabled=$false;source=$sf.src'
    '  })}'
    '}; '

    # ---- Output ---------------------------------------------------------
    'if($items.Count -eq 0){"[]"}'
    'else{$items|ConvertTo-Json -Compress -Depth 3}'
)


def _escape_ps_single(s: str) -> str:
    """Escape a value for embedding inside a PowerShell single-quoted string."""
    return s.replace("'", "''")


def _is_safe_name(name: str) -> bool:
    """
    Reject names that look like injection attempts before building PS strings.
    Only printable ASCII minus shell metacharacters is accepted.
    """
    return bool(name) and not re.search(r'[;&|`<>\r\n]', name)


def get_startup_items() -> dict:
    """
    Return all detected startup items with manageable/non-manageable flags.

    Returns:
        {
          'status': 'success' | 'error',
          'items':  [
            {
              'name':        str,
              'command':     str,
              'location':    str,
              'user':        str,
              'enabled':     bool,
              'source':      str,   # one of _MANAGEABLE_SOURCES or other
              'manageable':  bool,
              'source_label': str,
            },
            ...
          ],
          'error': str (only when status == 'error'),
        }
    """
    result = run_powershell(
        _QUERY_PS,
        timeout=20,
        description='Query startup items',
    )

    if result.is_error:
        logger.error('Startup query failed: %s', result.error)
        return {
            'status': 'error',
            'error': result.error or 'Error al consultar elementos de inicio.',
            'items': [],
        }

    raw_output = (result.output or '').strip()
    if not raw_output:
        return {'status': 'success', 'items': []}

    try:
        raw = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error('Startup JSON parse error: %s — output: %r', exc, raw_output[:200])
        return {
            'status': 'error',
            'error': 'No se pudo interpretar la respuesta del sistema.',
            'items': [],
        }

    if not isinstance(raw, list):
        raw = [raw] if isinstance(raw, dict) else []

    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get('source', ''))
        items.append({
            'name': str(entry.get('name', '')),
            'command': str(entry.get('command', '')),
            'location': str(entry.get('location', '')),
            'user': str(entry.get('user', '')),
            'enabled': bool(entry.get('enabled', True)),
            'source': source,
            'manageable': source in _MANAGEABLE_SOURCES,
            'source_label': _SOURCE_LABELS.get(source, 'Otro'),
        })

    return {'status': 'success', 'items': items}


# ---------------------------------------------------------------------------
# Internal helpers for registry and folder mutations
# ---------------------------------------------------------------------------

def _set_registry_approved(approved_path: str, name: str, enabled: bool) -> CommandResult:
    """
    Write or clear a StartupApproved binary value for a registry Run item.

    Disable: sets first byte to 0x03 (rest zeros) — item exists in Run key
             but Windows will skip it at boot.
    Enable:  sets first byte to 0x02 (rest zeros) — Windows will run it at boot.
             If no StartupApproved entry exists, Windows defaults to enabled,
             so enabling simply ensures the entry is set to 0x02.
    """
    safe_path = _escape_ps_single(approved_path)
    safe_name = _escape_ps_single(name)
    byte_val = '2,0,0,0,0,0,0,0,0,0,0,0' if enabled else '3,0,0,0,0,0,0,0,0,0,0,0'
    action_str = 'Habilitar' if enabled else 'Deshabilitar'

    ps = (
        f"$p='{safe_path}'; "
        f"if(-not (Test-Path $p)){{New-Item -Path $p -Force|Out-Null}}; "
        f"Set-ItemProperty -Path $p -Name '{safe_name}' "
        f"-Value ([byte[]]({byte_val})) -Type Binary -ErrorAction Stop"
    )
    return run_powershell(
        ps,
        requires_admin=True,
        timeout=15,
        description=f'{action_str} inicio (registro): {name}',
    )


def _set_folder_item(
    file_path: str, name: str, enabled: bool, requires_admin: bool = False,
) -> CommandResult:
    """
    Enable or disable a Startup folder item by renaming the .lnk file.

    Disable: renames  Name.lnk         → Name.lnk.disabled
    Enable:  renames  Name.lnk.disabled → Name.lnk

    requires_admin must be True for items in the Common Startup folder
    (C:\\ProgramData\\...), which is a system-level path.  User Startup
    folder items (C:\\Users\\...\\AppData\\...) do not need elevation.
    """
    safe_path = _escape_ps_single(file_path)
    safe_name = _escape_ps_single(name)
    action_str = 'Habilitar' if enabled else 'Deshabilitar'
    new_name = f'{safe_name}.lnk' if enabled else f'{safe_name}.lnk.disabled'

    ps = (
        f"Rename-Item -Path '{safe_path}' -NewName '{new_name}' "
        f"-Force -ErrorAction Stop"
    )
    return run_powershell(
        ps,
        requires_admin=requires_admin,
        timeout=10,
        description=f'{action_str} inicio (carpeta): {name}',
    )


# ---------------------------------------------------------------------------
# Public mutation function
# ---------------------------------------------------------------------------

def set_startup_item(name: str, location: str, enabled: bool) -> CommandResult:
    """
    Enable or disable a startup item identified by name + location.

    Validates the target against the live startup list before mutating.
    Rejects:
      - Items not found in the live list
      - Items with manageable=False (Task Scheduler / GPO / Store / unknown)
      - Items already in the requested state

    Args:
        name:     Exact item name as returned by get_startup_items().
        location: Exact location string as returned by get_startup_items().
        enabled:  True to enable, False to disable.

    Returns:
        CommandResult — caller checks .status and .output/.error.
    """
    # Basic injection guard before any PS call.
    if not _is_safe_name(name):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Nombre de inicio no válido: {name!r}',
        )

    # Validate against the live list.
    snapshot = get_startup_items()
    if snapshot['status'] == 'error':
        return CommandResult(
            status=CommandStatus.ERROR,
            error='No se pudo leer la lista de inicio para validar el objetivo.',
        )

    match = None
    for item in snapshot['items']:
        if item['name'] == name and item['location'] == location:
            match = item
            break

    if match is None:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=(
                f'Elemento "{name}" en "{location}" no encontrado en la lista activa. '
                'Recargue la página e intente de nuevo.'
            ),
        )

    if not match['manageable']:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=(
                f'"{name}" proviene de una fuente no gestionable '
                f'({match["source_label"]}). '
                'Esta herramienta no puede modificar entradas de Programador de tareas, '
                'GPO o aplicaciones de la Tienda.'
            ),
        )

    if match['enabled'] == enabled:
        state_str = 'habilitado' if enabled else 'deshabilitado'
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f'"{name}" ya está {state_str}. No se realizaron cambios.',
        )

    source = match['source']
    logger.info(
        '[STARTUP] %s "%s" (source=%s location=%s)',
        'Habilitando' if enabled else 'Deshabilitando', name, source, location,
    )

    if source == 'registry_hklm':
        app_path = (
            r'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion'
            r'\Explorer\StartupApproved\Run'
        )
        return _set_registry_approved(app_path, name, enabled)

    if source == 'registry_hkcu':
        app_path = (
            r'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion'
            r'\Explorer\StartupApproved\Run'
        )
        return _set_registry_approved(app_path, name, enabled)

    if source == 'folder_user':
        return _set_folder_item(match['command'], name, enabled, requires_admin=False)

    if source == 'folder_common':
        # Common Startup is under C:\ProgramData\ — writes require admin.
        return _set_folder_item(match['command'], name, enabled, requires_admin=True)

    return CommandResult(
        status=CommandStatus.ERROR,
        error=f'Fuente no reconocida: {source}',
    )
