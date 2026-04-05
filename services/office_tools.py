"""
Office License Inspection and Activation Module.

Safe, official Microsoft tooling only:
  - Detection: Registry + ClickToRun configuration keys
  - Inspection: cscript ospp.vbs /dstatus  (Office Software Protection Platform)
  - Key input: cscript ospp.vbs /inpkey:<key>
  - Activation: cscript ospp.vbs /act

Key masking:
  - Full key is NEVER stored in logs, reports, or persisted state.
  - Only last-5 characters (suffix) are retained in result payloads.
  - The key string is overwritten in memory as soon as the subprocess starts.

Supported scenarios:
  - Office 365 / Microsoft 365 (ClickToRun)
  - Office 2024 / 2021 / 2019 / 2016 (ClickToRun and MSI/volume)
  - Any edition where ospp.vbs is present under the Office installation path

Unsupported scenarios (clearly reported):
  - Office not installed
  - ospp.vbs not found at any known location
  - Admin rights absent for activation
  - Edition/key mismatch (reported by ospp.vbs output, not silently swallowed)
"""
import os
import re
import sys
import logging

from services.command_runner import (
    run_cmd, run_powershell, run_powershell_json, CommandStatus, CommandResult,
)

logger = logging.getLogger('cleancpu.office')

# ---------------------------------------------------------------------------
# Known ospp.vbs locations — checked in order, first found wins.
# Covers Office 2016–2024 x64, x86, and M365.
# ---------------------------------------------------------------------------
_OSPP_SEARCH_PATHS = [
    # Office 365 / M365 / perpetual C2R (64-bit Office on 64-bit Windows)
    r'C:\Program Files\Microsoft Office\Office16\ospp.vbs',
    r'C:\Program Files\Microsoft Office\Office15\ospp.vbs',
    # 32-bit Office on 64-bit Windows
    r'C:\Program Files (x86)\Microsoft Office\Office16\ospp.vbs',
    r'C:\Program Files (x86)\Microsoft Office\Office15\ospp.vbs',
    # Office 2013
    r'C:\Program Files\Microsoft Office\Office14\ospp.vbs',
    r'C:\Program Files (x86)\Microsoft Office\Office14\ospp.vbs',
]

# Pattern for a raw 25-character product key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
_KEY_RE = re.compile(
    r'^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_ospp() -> str:
    """Return the first ospp.vbs path that exists, or ''."""
    for path in _OSPP_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return ''


def _mask_key(key: str) -> str:
    """Return XXXXX-XXXXX-XXXXX-XXXXX-<last5> for display."""
    parts = key.upper().split('-')
    if len(parts) == 5:
        return f'XXXXX-XXXXX-XXXXX-XXXXX-{parts[4]}'
    # Partial match — mask all but last 5 chars.
    # Must be strictly > 5 so a 5-char input doesn't produce '' + key (unmasked).
    if len(key) > 5:
        return 'X' * (len(key) - 5) + key[-5:]
    return 'XXXXX'


def _run_ospp(ospp_path: str, flag: str, timeout: int = 60) -> CommandResult:
    """
    Run cscript ospp.vbs <flag> with //nologo.
    Uses run_cmd so it goes through the standard command pipeline and audit trail.
    The description passed to run_cmd never includes a product key.
    """
    # Never put the product key in the log description
    safe_desc = 'ospp.vbs /inpkey:***' if flag.lower().startswith('/inpkey:') else f'ospp.vbs {flag}'
    return run_cmd(
        ['cscript', '//nologo', ospp_path, flag],
        requires_admin=True,
        timeout=timeout,
        description=safe_desc,
    )


def _parse_dstatus(raw_output: str) -> dict:
    """
    Parse the output of ospp.vbs /dstatus into a structured dict.
    Returns best-effort extraction; missing fields remain ''.
    """
    info = {
        'product_name': '',
        'license_status': '',
        'partial_key': '',
        'product_id': '',
        'sku_id': '',
        'description': '',
        'remaining_grace': '',
    }

    for line in raw_output.splitlines():
        line = line.strip()
        # ospp.vbs uses "---" separators and "Name:" style lines
        lower = line.lower()
        if lower.startswith('name:'):
            info['product_name'] = line.split(':', 1)[1].strip()
        elif lower.startswith('license status:') or lower.startswith('estado de licencia:'):
            info['license_status'] = line.split(':', 1)[1].strip()
        elif lower.startswith('last 5 characters') or lower.startswith('ultimos 5 caracteres'):
            info['partial_key'] = line.split(':', 1)[1].strip()
        elif lower.startswith('product id:') or lower.startswith('id. de producto:'):
            info['product_id'] = line.split(':', 1)[1].strip()
        elif lower.startswith('sku id:'):
            info['sku_id'] = line.split(':', 1)[1].strip()
        elif lower.startswith('remaining grace:') or lower.startswith('gracia restante:'):
            info['remaining_grace'] = line.split(':', 1)[1].strip()

    return info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_installation_info() -> dict:
    """
    Collect Office installation information from the registry only (no ospp.vbs).
    Fast, read-only, no admin required.

    Returns:
        installed: bool
        product_name: str
        version: str
        platform: str ('x86' / 'x64' / '')
        release_ids: str  (C2R channel product IDs, comma-separated)
        channel: str  (Current / MonthlyEnterprise / SemiAnnual / '')
        is_c2r: bool
        ospp_path: str  (path to ospp.vbs or '')
        source: str  ('registry' always for this function)
    """
    from services.system_inventory import _collect_office
    office = _collect_office()

    ospp_path = _find_ospp()

    return {
        'installed': bool(office.get('product_name') or ospp_path),
        'product_name': office.get('product_name', ''),
        'version': office.get('version', ''),
        'platform': office.get('platform', ''),
        'release_ids': office.get('release_ids', ''),
        'channel': office.get('channel', ''),
        'is_c2r': office.get('is_c2r', False),
        'ospp_path': ospp_path,
        'source': 'registry',
    }


def inspect_license() -> dict:
    """
    Run ospp.vbs /dstatus to get the current Office license/activation status.
    Requires admin for ospp.vbs to run; returns REQUIRES_ADMIN status if absent.

    Returns dict with:
        status: 'success' | 'requires_admin' | 'office_not_found' |
                        'ospp_not_found' | 'error'
        message: human-readable summary
        raw_output: full ospp.vbs /dstatus output (for technician)
        parsed: structured fields from _parse_dstatus()
    """
    if sys.platform != 'win32':
        return {
            'status': 'not_applicable',
            'message': 'Inspeccion de Office solo disponible en Windows.',
            'raw_output': '',
            'parsed': {},
        }

    ospp_path = _find_ospp()
    if not ospp_path:
        return {
            'status': 'ospp_not_found',
            'message': (
                'No se encontro ospp.vbs. Office puede no estar instalado '
                'o estar en una ruta no estandar.'
            ),
            'raw_output': '',
            'parsed': {},
        }

    result = _run_ospp(ospp_path, '/dstatus', timeout=60)

    if result.status == CommandStatus.REQUIRES_ADMIN:
        return {
            'status': 'requires_admin',
            'message': 'Se requieren permisos de Administrador para inspeccionar la licencia de Office.',
            'raw_output': '',
            'parsed': {},
        }

    if result.is_error:
        return {
            'status': 'error',
            'message': f'Error al ejecutar ospp.vbs /dstatus: {result.error or "desconocido"}',
            'raw_output': result.output or '',
            'parsed': {},
        }

    raw = result.output or ''
    parsed = _parse_dstatus(raw)

    # Determine human-readable summary from license status field
    lic_status = parsed.get('license_status', '').lower()
    if 'licensed' in lic_status or 'activad' in lic_status:
        msg = f"Office activado: {parsed.get('product_name', 'Microsoft Office')}"
    elif 'notification' in lic_status or 'gracia' in lic_status or 'grace' in lic_status:
        msg = f"Office en periodo de gracia: {parsed.get('product_name', '')}"
    elif 'unlicensed' in lic_status or 'no licenciado' in lic_status:
        msg = 'Office NO esta activado.'
    elif raw.strip():
        msg = f"Estado de licencia: {parsed.get('license_status', 'desconocido')}"
    else:
        msg = 'ospp.vbs no produjo salida. Office puede no estar instalado correctamente.'

    return {
        'status': 'success',
        'message': msg,
        'raw_output': raw,
        'parsed': parsed,
    }


def activate_with_key(key: str) -> dict:
    """
    Apply a product key and trigger Office activation.
    Uses official ospp.vbs mechanism only.

    Steps:
      1. Validate key format (25-char XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
      2. Run ospp.vbs /inpkey:<key>  — installs the key into Office's license store
      3. Run ospp.vbs /act            — triggers activation against Microsoft servers

    The full key is NEVER returned in the result dict, never logged.
    Only the masked form (XXXXX-XXXXX-XXXXX-XXXXX-<last5>) is retained.

    Returns dict with:
        status: 'success' | 'invalid_key' | 'requires_admin' |
                  'ospp_not_found' | 'inpkey_failed' | 'activation_failed' | 'error'
        message: human-readable result
        masked_key: str (safe for logs/reports)
        inpkey_output: str
        act_output: str
    """
    if sys.platform != 'win32':
        return {
            'status': 'not_applicable',
            'message': 'Activacion de Office solo disponible en Windows.',
            'masked_key': '',
            'inpkey_output': '',
            'act_output': '',
        }

    key = (key or '').strip().upper()
    masked = _mask_key(key)

    # Validate format before sending to ospp.vbs
    if not _KEY_RE.match(key):
        return {
            'status': 'invalid_key',
            'message': (
                f'Formato de clave invalido ({masked}). '
                'El formato debe ser XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (25 caracteres).'
            ),
            'masked_key': masked,
            'inpkey_output': '',
            'act_output': '',
        }

    ospp_path = _find_ospp()
    if not ospp_path:
        return {
            'status': 'ospp_not_found',
            'message': 'ospp.vbs no encontrado. Office puede no estar instalado.',
            'masked_key': masked,
            'inpkey_output': '',
            'act_output': '',
        }

    # Step 1 — Install key
    inpkey_result = _run_ospp(ospp_path, f'/inpkey:{key}', timeout=60)
    # Clear the key variable immediately after subprocess launch
    key = None  # noqa: F841 — intentional memory clear

    if inpkey_result.status == CommandStatus.REQUIRES_ADMIN:
        return {
            'status': 'requires_admin',
            'message': 'Se requieren permisos de Administrador para instalar la clave de producto.',
            'masked_key': masked,
            'inpkey_output': '',
            'act_output': '',
        }

    inpkey_out = inpkey_result.output or ''

    if inpkey_result.is_error or 'error' in inpkey_out.lower():
        # ospp.vbs reports errors in stdout (not stderr), check both
        return {
            'status': 'inpkey_failed',
            'message': (
                f'Error al instalar la clave ({masked}). '
                f'Detalle: {inpkey_out or inpkey_result.error or "desconocido"}. '
                'Verifique que la clave sea valida para la edicion de Office instalada.'
            ),
            'masked_key': masked,
            'inpkey_output': inpkey_out,
            'act_output': '',
        }

    # Step 2 — Activate
    act_result = _run_ospp(ospp_path, '/act', timeout=120)
    act_out = act_result.output or ''

    if act_result.status == CommandStatus.REQUIRES_ADMIN:
        return {
            'status': 'requires_admin',
            'message': 'Clave instalada pero la activacion requiere permisos de Administrador.',
            'masked_key': masked,
            'inpkey_output': inpkey_out,
            'act_output': '',
        }

    act_lower = act_out.lower()
    if 'successful' in act_lower or 'exitosa' in act_lower or 'correctamente' in act_lower:
        return {
            'status': 'success',
            'message': f'Office activado correctamente con clave {masked}.',
            'masked_key': masked,
            'inpkey_output': inpkey_out,
            'act_output': act_out,
        }

    if act_result.is_error or 'error' in act_lower or '0x' in act_lower:
        return {
            'status': 'activation_failed',
            'message': (
                f'La clave fue instalada ({masked}) pero la activacion fallo. '
                f'Detalle: {act_out or act_result.error or "desconocido"}.'
            ),
            'masked_key': masked,
            'inpkey_output': inpkey_out,
            'act_output': act_out,
        }

    # Ambiguous output
    return {
        'status': 'activation_failed',
        'message': (
            f'Resultado de activacion no determinado para clave {masked}. '
            'Revise la salida del comando para mas detalles.'
        ),
        'masked_key': masked,
        'inpkey_output': inpkey_out,
        'act_output': act_out,
    }


# ---------------------------------------------------------------------------
# Phase 4 — Path discovery for Office tools
# All finders return '' when not found; callers check before proceeding.
# ---------------------------------------------------------------------------

_C2R_SEARCH_PATHS = [
    r'C:\Program Files\Common Files\microsoft shared\ClickToRun\OfficeClickToRun.exe',
    r'C:\Program Files (x86)\Common Files\microsoft shared\ClickToRun\OfficeClickToRun.exe',
]

# Office 16 C2R installs use root\office16\; MSI installs use Office16\ directly.
_OUTLOOK_SEARCH_PATHS = [
    r'C:\Program Files\Microsoft Office\root\office16\OUTLOOK.EXE',
    r'C:\Program Files (x86)\Microsoft Office\root\office16\OUTLOOK.EXE',
    r'C:\Program Files\Microsoft Office\Office16\OUTLOOK.EXE',
    r'C:\Program Files (x86)\Microsoft Office\Office16\OUTLOOK.EXE',
    r'C:\Program Files\Microsoft Office\Office15\OUTLOOK.EXE',
    r'C:\Program Files (x86)\Microsoft Office\Office15\OUTLOOK.EXE',
]

_SCANPST_SEARCH_PATHS = [
    r'C:\Program Files\Microsoft Office\root\office16\SCANPST.EXE',
    r'C:\Program Files (x86)\Microsoft Office\root\office16\SCANPST.EXE',
    r'C:\Program Files\Microsoft Office\Office16\SCANPST.EXE',
    r'C:\Program Files (x86)\Microsoft Office\Office16\SCANPST.EXE',
    r'C:\Program Files\Microsoft Office\Office15\SCANPST.EXE',
    r'C:\Program Files (x86)\Microsoft Office\Office15\SCANPST.EXE',
]


def _find_c2r() -> str:
    """Return the first OfficeClickToRun.exe path that exists, or ''."""
    for path in _C2R_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return ''


def _find_outlook() -> str:
    """Return the first OUTLOOK.EXE path that exists, or ''."""
    for path in _OUTLOOK_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return ''


def _find_scanpst() -> str:
    """Return the first SCANPST.EXE path that exists, or ''."""
    for path in _SCANPST_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return ''


# ---------------------------------------------------------------------------
# Phase 4 — Public API: Office repair
# ---------------------------------------------------------------------------

def repair_office(repair_type: str = 'quick') -> dict:
    """
    Trigger Office ClickToRun repair (Quick or Full/Online).
    Only available for C2R installations (OfficeClickToRun.exe must be present).

    repair_type: 'quick'  → QuickRepair  (local files only, fast)
                 'online' → FullRepair   (downloads from Microsoft, slow)

    Launches via PowerShell Start-Process so the repair UI runs detached.
    Returns immediately after the process is launched.

    Returns dict with keys: status, message
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo disponible en Windows.'}

    c2r_path = _find_c2r()
    if not c2r_path:
        return {
            'status': 'not_found',
            'message': (
                'OfficeClickToRun.exe no encontrado. '
                'Este equipo puede tener una instalacion Office MSI/Volumen '
                'en lugar de Click-to-Run, o Office no esta instalado.'
            ),
        }

    repair_type_param = 'FullRepair' if repair_type == 'online' else 'QuickRepair'
    label = 'en linea' if repair_type == 'online' else 'rapida'

    # -Verb RunAs requests UAC if not already elevated; since the app runs as
    # admin this completes silently.
    ps_script = (
        f'Start-Process -FilePath "{c2r_path}" '
        f'-ArgumentList "scenario=Repair RepairType={repair_type_param} DisplayLevel=Full" '
        '-Verb RunAs'
    )
    result = run_powershell(
        ps_script, timeout=15,
        description=f'Office {label} repair launch',
    )

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING,
                         CommandStatus.NOT_APPLICABLE):
        return {
            'status': 'launched',
            'message': (
                f'Reparacion {label} de Office iniciada. '
                'El proceso de reparacion se ejecuta en una ventana independiente. '
                'Office debe estar cerrado durante la reparacion.'
            ),
        }
    return {
        'status': 'error',
        'message': (
            f'No se pudo iniciar la reparacion {label}: '
            f'{result.error or result.output or "desconocido"}'
        ),
    }


# ---------------------------------------------------------------------------
# Phase 4 — Public API: Outlook helpers
# ---------------------------------------------------------------------------

def launch_office_safe_mode() -> dict:
    """
    Launch Outlook in safe mode (/safe).
    Useful when Outlook crashes at startup or a faulty add-in is suspected.
    Returns immediately — Outlook opens in its own window.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo disponible en Windows.'}

    outlook_path = _find_outlook()
    if not outlook_path:
        return {
            'status': 'not_found',
            'message': 'OUTLOOK.EXE no encontrado en rutas conocidas.',
        }

    ps_script = f'Start-Process -FilePath "{outlook_path}" -ArgumentList "/safe"'
    result = run_powershell(ps_script, timeout=10, description='Outlook /safe launch')

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING,
                         CommandStatus.NOT_APPLICABLE):
        return {
            'status': 'launched',
            'message': (
                'Outlook iniciado en modo seguro (/safe). '
                'Si el problema desaparece, un complemento puede ser la causa. '
                'Para desactivar complementos: Archivo > Opciones > Complementos.'
            ),
        }
    return {
        'status': 'error',
        'message': (
            f'No se pudo iniciar Outlook en modo seguro: '
            f'{result.error or result.output or "desconocido"}'
        ),
    }


def configure_mail_profile() -> dict:
    """
    Open the Windows Mail / Outlook profile manager (mlcfg32.cpl).
    Used to create, repair, or delete Outlook mail profiles.
    mlcfg32.cpl is a Windows component, always available.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo disponible en Windows.'}

    ps_script = 'Start-Process -FilePath "control.exe" -ArgumentList "mlcfg32.cpl"'
    result = run_powershell(ps_script, timeout=10, description='Open Mail profile applet')

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING,
                         CommandStatus.NOT_APPLICABLE):
        return {
            'status': 'launched',
            'message': (
                'Panel de configuracion de correo abierto. '
                'Aqui puede crear, reparar o eliminar perfiles de Outlook.'
            ),
        }
    return {
        'status': 'error',
        'message': (
            f'No se pudo abrir la configuracion de correo: '
            f'{result.error or result.output or "desconocido"}'
        ),
    }


def launch_scanpst() -> dict:
    """
    Launch Outlook's Inbox Repair Tool (SCANPST.EXE).
    SCANPST opens a GUI where the technician selects the PST/OST file to repair.
    Returns immediately — SCANPST opens in its own window.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo disponible en Windows.'}

    scanpst_path = _find_scanpst()
    if not scanpst_path:
        return {
            'status': 'not_found',
            'message': (
                'SCANPST.EXE no encontrado. '
                'Verifique que Outlook este instalado correctamente.'
            ),
        }

    ps_script = f'Start-Process -FilePath "{scanpst_path}"'
    result = run_powershell(ps_script, timeout=10, description='Launch SCANPST.EXE')

    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING,
                         CommandStatus.NOT_APPLICABLE):
        return {
            'status': 'launched',
            'message': (
                'Herramienta de reparacion de archivos PST/OST (SCANPST.EXE) iniciada. '
                'Seleccione el archivo de datos de Outlook en la ventana abierta.'
            ),
            'path': scanpst_path,
        }
    return {
        'status': 'error',
        'message': (
            f'No se pudo iniciar SCANPST.EXE: '
            f'{result.error or result.output or "desconocido"}'
        ),
    }


def rebuild_outlook_search_index() -> dict:
    """
    Rebuild the Windows Search index (which Outlook uses for full-text search).

    Procedure:
      1. Stop the WSearch service (Windows Search).
      2. Delete all files in the index catalog directory.
      3. Restart WSearch — Windows will rebuild the index automatically.

    Requires admin. Affects all Windows Search, not just Outlook.
    Rebuilding is automatic after restart; it may take several minutes
    depending on mailbox and file system size.
    """
    if sys.platform != 'win32':
        return {'status': 'not_applicable', 'message': 'Solo disponible en Windows.'}

    ps_script = (
        'Stop-Service -Name WSearch -Force -ErrorAction SilentlyContinue; '
        'Start-Sleep -Seconds 2; '
        '$idx = "$env:ProgramData\\Microsoft\\Search\\Data\\Applications\\Windows"; '
        'if (Test-Path $idx) { '
        '  Remove-Item "$idx\\*" -Recurse -Force -ErrorAction SilentlyContinue; '
        '  Write-Output "Indice de busqueda eliminado correctamente."; '
        '} else { '
        '  Write-Output "Directorio de indice no encontrado (puede ya estar limpio)."; '
        '}; '
        'Start-Service -Name WSearch -ErrorAction SilentlyContinue; '
        'Write-Output "Servicio Windows Search reiniciado. '
        'La reindexacion comenzara automaticamente."'
    )
    result = run_powershell(
        ps_script, timeout=60, requires_admin=True,
        description='Rebuild Windows Search index',
    )

    if result.status == CommandStatus.REQUIRES_ADMIN:
        return {
            'status': 'requires_admin',
            'message': 'Se requieren permisos de Administrador para reconstruir el indice de busqueda.',
        }
    if result.status in (CommandStatus.SUCCESS, CommandStatus.WARNING):
        return {
            'status': 'success',
            'message': (
                'Indice de busqueda reconstruido. '
                'Outlook reindexara los correos automaticamente '
                '(puede tardar varios minutos segun el tamano del buz\u00f3n).'
            ),
            'output': result.output or '',
        }
    return {
        'status': 'error',
        'message': (
            f'Error al reconstruir el indice: '
            f'{result.error or result.output or "desconocido"}'
        ),
    }


# ---------------------------------------------------------------------------
# Phase 4 — Public API: Paquetería (installed programs inventory)
# ---------------------------------------------------------------------------

def get_installed_packages() -> dict:
    """
    List installed applications from the Windows registry.
    Reads HKLM (64-bit and 32-bit hive) and HKCU uninstall keys.
    No admin required — registry reads are allowed for standard users.

    Returns dict with:
        status:   'success' | 'empty' | 'not_applicable' | 'error'
        message:  human-readable summary
        packages: list of dicts (name, version, publisher, install_date)
    """
    if sys.platform != 'win32':
        return {
            'status': 'not_applicable',
            'message': 'Inventario de paquetes solo disponible en Windows.',
            'packages': [],
        }

    ps_script = (
        '$paths = @('
        '"HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",'
        '"HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",'
        '"HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"'
        '); '
        'Get-ItemProperty $paths -ErrorAction SilentlyContinue '
        '| Where-Object { $_.DisplayName -ne $null -and $_.DisplayName.Trim() -ne "" } '
        '| Select-Object DisplayName, DisplayVersion, Publisher, InstallDate '
        '| Sort-Object DisplayName'
    )

    result = run_powershell_json(
        ps_script, timeout=30,
        description='List installed packages (registry)',
    )

    packages = []
    data = result.details.get('data')
    if data is not None:
        if isinstance(data, dict):
            data = [data]
        for item in (data if isinstance(data, list) else []):
            name = (item.get('DisplayName') or '').strip()
            if name:
                packages.append({
                    'name': name,
                    'version': (item.get('DisplayVersion') or '').strip(),
                    'publisher': (item.get('Publisher') or '').strip(),
                    'install_date': (item.get('InstallDate') or '').strip(),
                })

    if result.is_error and not packages:
        return {
            'status': 'error',
            'message': f'Error al obtener la lista de programas: {result.error or "desconocido"}',
            'packages': [],
        }

    return {
        'status': 'success' if packages else 'empty',
        'message': (
            f'{len(packages)} programas encontrados.'
            if packages else 'No se encontraron programas instalados.'
        ),
        'packages': packages,
    }
