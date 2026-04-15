"""
SMB Repair Workflow — diagnostic and remediation service layer.

Implements the full modular SMB access troubleshooting workflow based on
the confirmed production incident pattern:
  - Client could ping server; TCP 445 reachable; other PCs connected fine.
  - Access to the target share failed.
  - Root cause: RequireSecuritySignature = True on the client.
  - Fix: Set-SmbClientConfiguration -RequireSecuritySignature $false -Force
         (EnableSecuritySignature remains True — signing still offered/accepted
          when the server supports it; only the mandatory requirement is removed.)

All read-only functions return structured dicts.
All mutating functions return CommandResult (go through governance layer).

Environment limitations:
  - Get-SmbClientConfiguration requires Windows 8+ / Server 2012 R2+.
  - Test-Connection / Test-NetConnection require WinRM-accessible network stack.
  - LanmanWorkstation restart briefly drops existing SMB sessions.
  - AllowInsecureGuestAuth registry key requires a LanmanWorkstation restart
    to take effect; service restart is included in allow_insecure_guest().
  - classify_smb_issue() is pure Python — no PowerShell round-trip.
  - run_full_smb_diagnosis() is synchronous and runs all sub-queries in sequence;
    may take up to 60s on slow networks due to ping + TCP 445 timeouts.

Not in scope for this module:
  - SMB server-side configuration (Get-SmbServerConfiguration)
  - Drive letter persistence across reboots via registry (use net use /persistent)
  - Kerberos / AD credential issues
  - GPO-enforced settings (detected but not remediated)
"""
import re
import logging
from datetime import datetime

from services.command_runner import (
    run_powershell, run_powershell_json, CommandStatus, CommandResult
)

logger = logging.getLogger('cleancpu.smb_repair')


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_HOST_RE = re.compile(r'^[a-zA-Z0-9._-]{1,253}$')
_HOST_FORBIDDEN = set('"\'`;|&<>()\n\r\\ /')

_UNC_RE = re.compile(
    r'^\\\\[a-zA-Z0-9._-]{1,253}\\[a-zA-Z0-9 ._-]{1,80}'
    r'(\\[a-zA-Z0-9 ._-]{1,260})*$'
)
_UNC_FORBIDDEN = set('"\'`$;|&<>()\n\r')

_DRIVE_LETTER_RE = re.compile(r'^[A-Za-z]$')


def _is_safe_host(host: str) -> bool:
    if not isinstance(host, str) or not host:
        return False
    if any(c in _HOST_FORBIDDEN for c in host):
        return False
    return bool(_HOST_RE.match(host))


def _is_safe_unc_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    if any(c in _UNC_FORBIDDEN for c in path):
        return False
    return bool(_UNC_RE.match(path))


def _is_safe_drive_letter(letter: str) -> bool:
    return bool(letter and isinstance(letter, str) and _DRIVE_LETTER_RE.match(letter))


def _extract_server(unc_path: str) -> str:
    parts = unc_path.lstrip('\\').split('\\')
    return parts[0] if parts else ''


def _norm_json(result, description: str) -> tuple:
    """Extract raw dict from run_powershell_json result. Returns (raw_dict, error_str)."""
    raw = result.details.get('data') if result.details else None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if result.is_error or not isinstance(raw, dict):
        err = result.error or f'Error al ejecutar: {description}'
        return None, err
    return raw, None


# ---------------------------------------------------------------------------
# Layer 1 — Read-only diagnostics
# ---------------------------------------------------------------------------

_SMB_SERVICES_PS = (
    "$r=[PSCustomObject]@{lanman_server=$null;lanman_workstation=$null;lmhosts=$null};"
    "$s=Get-Service LanmanServer -EA SilentlyContinue;"
    "if($s){$r.lanman_server=[PSCustomObject]@{"
    "status=$s.Status.ToString();start_type=$s.StartType.ToString()}};"
    "$s=Get-Service LanmanWorkstation -EA SilentlyContinue;"
    "if($s){$r.lanman_workstation=[PSCustomObject]@{"
    "status=$s.Status.ToString();start_type=$s.StartType.ToString()}};"
    "$s=Get-Service lmhosts -EA SilentlyContinue;"
    "if($s){$r.lmhosts=[PSCustomObject]@{"
    "status=$s.Status.ToString();start_type=$s.StartType.ToString()}};"
    "$r|ConvertTo-Json -Compress -Depth 3"
)


def check_smb_services() -> dict:
    """
    Query state of LanmanServer, LanmanWorkstation, and lmhosts services.

    Returns:
        status: 'success' | 'error'
        services: {lanman_server, lanman_workstation, lmhosts} each with
                  {status: str, start_type: str} or null if absent.
    """
    result = run_powershell_json(_SMB_SERVICES_PS, description='Check SMB services')
    raw, err = _norm_json(result, 'SMB services check')
    if err:
        return {'status': 'error', 'message': err, 'services': {}}

    def _svc(obj):
        if not isinstance(obj, dict):
            return None
        return {'status': obj.get('status'), 'start_type': obj.get('start_type')}

    return {
        'status': 'success',
        'services': {
            'lanman_server': _svc(raw.get('lanman_server')),
            'lanman_workstation': _svc(raw.get('lanman_workstation')),
            'lmhosts': _svc(raw.get('lmhosts')),
        },
    }


_SMB_CLIENT_CONFIG_PS = (
    "try{"
    "$c=Get-SmbClientConfiguration -EA Stop;"
    "[PSCustomObject]@{"
    "RequireSecuritySignature=$c.RequireSecuritySignature;"
    "EnableSecuritySignature=$c.EnableSecuritySignature;"
    "EnableInsecureGuestLogons=$c.EnableInsecureGuestLogons;"
    "RequireEncryption=$c.RequireEncryption;"
    "BlockNTLM=$c.BlockNTLM"
    "}|ConvertTo-Json -Compress"
    "}catch{"
    "[PSCustomObject]@{error=$_.Exception.Message}|ConvertTo-Json -Compress"
    "}"
)

_SMB_CONFIG_KEYS = (
    'RequireSecuritySignature',
    'EnableSecuritySignature',
    'EnableInsecureGuestLogons',
    'RequireEncryption',
    'BlockNTLM',
)


def get_smb_client_config() -> dict:
    """
    Query Get-SmbClientConfiguration and return key security parameters.

    RequireSecuritySignature = True is the primary cause of the confirmed
    incident pattern ("configured to require SMB signing").

    Returns:
        status: 'success' | 'error'
        config: dict of bool values for each key parameter (null if unavailable)
    """
    result = run_powershell_json(_SMB_CLIENT_CONFIG_PS, description='Get SMB client config')
    raw, err = _norm_json(result, 'SMB client config')
    if err:
        return {'status': 'error', 'message': err, 'config': {}}

    if 'error' in raw:
        return {
            'status': 'error',
            'message': raw['error'],
            'config': {},
        }

    return {
        'status': 'success',
        'config': {k: raw.get(k) for k in _SMB_CONFIG_KEYS},
    }


def test_host_reachability(host: str) -> dict:
    """
    Test ping + TCP 445 reachability for a given host.

    Returns:
        status: 'success' | 'error'
        host: validated hostname or IP
        reachability: {ping: bool|null, tcp445: bool|null}
    """
    if not _is_safe_host(host):
        return {
            'status': 'error',
            'message': f'Host no válido o contiene caracteres no permitidos: {host!r}',
            'reachability': {},
            'host': host,
        }

    ps = (
        f"$h='{host}';"
        "$r=[PSCustomObject]@{ping=$null;tcp445=$null};"
        "try{$r.ping=[bool](Test-Connection $h -Count 2 -Quiet -EA Stop"
        " -WarningAction SilentlyContinue)}catch{$r.ping=$false};"
        "try{$r.tcp445=[bool](Test-NetConnection $h -Port 445"
        " -InformationLevel Quiet -EA Stop"
        " -WarningAction SilentlyContinue 2>$null)}catch{$r.tcp445=$false};"
        "$r|ConvertTo-Json -Compress"
    )
    result = run_powershell_json(ps, description=f'Test reachability to {host}', timeout=35)
    raw, err = _norm_json(result, f'reachability test to {host}')
    if err:
        return {'status': 'error', 'message': err, 'reachability': {}, 'host': host}

    return {
        'status': 'success',
        'host': host,
        'reachability': {
            'ping': raw.get('ping'),
            'tcp445': raw.get('tcp445'),
        },
    }


def test_unc_access(unc_path: str) -> dict:
    """
    Attempt Get-ChildItem on a UNC path and capture error details.

    This reveals the actual SMB-layer error (signing mismatch, access denied,
    path not found, guest blocked) that the technician needs to classify.

    Returns:
        status: 'success' | 'error'
        unc_path: validated path
        access: {accessible: bool, error_msg: str|null, item_count: int|null}
    """
    if not _is_safe_unc_path(unc_path):
        return {
            'status': 'error',
            'message': f'Ruta UNC no válida: {unc_path!r}',
            'access': {},
            'unc_path': unc_path,
        }

    ps = (
        f"$unc='{unc_path}';"
        "$r=[PSCustomObject]@{accessible=$null;error_msg=$null;item_count=$null};"
        "try{"
        "$items=@(Get-ChildItem $unc -ErrorAction Stop -Force);"
        "$r.accessible=$true;"
        "$r.item_count=$items.Count"
        "}catch{"
        "$r.accessible=$false;"
        "$r.error_msg=$_.Exception.Message"
        "};"
        "$r|ConvertTo-Json -Compress"
    )
    result = run_powershell_json(
        ps, description=f'Test UNC access to {unc_path}', timeout=30
    )
    raw, err = _norm_json(result, f'UNC access test {unc_path}')
    if err:
        return {'status': 'error', 'message': err, 'access': {}, 'unc_path': unc_path}

    return {
        'status': 'success',
        'unc_path': unc_path,
        'access': {
            'accessible': raw.get('accessible'),
            'error_msg': raw.get('error_msg'),
            'item_count': raw.get('item_count'),
        },
    }


def get_mapped_drives() -> dict:
    """
    List currently mapped network drives (FileSystem PSDrives with UNC DisplayRoot).

    Returns:
        status: 'success' | 'error'
        drives: list of {Name, DisplayRoot}
    """
    ps = (
        "$drives=@(Get-PSDrive -PSProvider FileSystem -EA SilentlyContinue"
        "|Where-Object{$_.DisplayRoot -like '\\\\*'}"
        "|Select-Object Name,DisplayRoot);"
        "[PSCustomObject]@{drives=$drives}|ConvertTo-Json -Compress -Depth 3"
    )
    result = run_powershell_json(ps, description='List mapped network drives')
    raw, err = _norm_json(result, 'mapped drives list')
    if err:
        return {'status': 'error', 'message': err, 'drives': []}

    drives = raw.get('drives', [])
    if isinstance(drives, dict):
        drives = [drives]
    elif not isinstance(drives, list):
        drives = []

    return {'status': 'success', 'drives': drives}


# ---------------------------------------------------------------------------
# Layer 2 — Detection / classification engine (pure Python, no PS)
# ---------------------------------------------------------------------------

# Phrases that indicate SMB signing mismatch in error output.
# Matched case-insensitively against the raw error string from Get-ChildItem.
_SIGNING_PHRASES = frozenset([
    'smb signing',
    'configured to require smb signing',
    'client requires smb signing',
    'require smb signing',
    'security signature',
    'signing is required',
    'firma smb',
    'requiere firma smb',
    'firmar smb',
])

_GUEST_PHRASES = frozenset([
    'guest',
    'insecure guest',
    'invitado',
    'acceso de invitado',
])

_ACCESS_DENIED_PHRASES = frozenset([
    'access denied',
    'acceso denegado',
    'logon failure',
    'error al iniciar sesion',
    'wrong password',
    'invalid password',
    '0x80070005',
])

_PATH_NOT_FOUND_PHRASES = frozenset([
    'network path was not found',
    'network path not found',
    'no se encontro la ruta de red',
    'path not found',
    'no se encontro',
    '0x80070035',
    'bad network name',
    'nombre de red incorrecto',
])


def classify_smb_issue(findings: dict) -> dict:
    """
    Classify the most likely SMB access problem from collected findings.

    Implements the detection logic from the confirmed production incident.
    The 'smb_signing_mismatch' classification triggers when:
      - RequireSecuritySignature = True on the local client, AND
      - TCP 445 is reachable, AND
      - UNC access fails (with or without signing error text)
    Confidence is 'high' when the error text also contains signing phrases.

    Args:
        findings: dict with optional keys:
            services: from check_smb_services()
            client_config: from get_smb_client_config()
            reachability: from test_host_reachability()
            unc_access: from test_unc_access()

    Returns dict with:
        cause, confidence, label, recommended_action, risk_level, details
    """
    services = findings.get('services', {})
    config = findings.get('client_config', {})
    reach = findings.get('reachability', {})
    access = findings.get('unc_access', {})

    details = []

    # --- Check services first ---
    lmw = services.get('lanman_workstation') or {}
    if lmw and lmw.get('status') not in ('Running', None):
        return {
            'cause': 'smb_services_down',
            'confidence': 'high',
            'label': 'Servicio SMB cliente detenido',
            'recommended_action': 'smb.restart_lanman',
            'risk_level': 'RISKY',
            'details': [
                f"LanmanWorkstation: {lmw.get('status', '?')} "
                f"(inicio: {lmw.get('start_type', '?')})"
            ],
        }

    # --- No UNC access data: classify what we can ---
    if not access:
        if reach.get('ping') is False and reach.get('tcp445') is False:
            return {
                'cause': 'host_unreachable',
                'confidence': 'high',
                'label': 'Servidor no alcanzable',
                'recommended_action': None,
                'risk_level': 'INFO',
                'details': ['Ping y TCP 445 fallaron. Verifique red, nombre/IP del servidor.'],
            }
        return {
            'cause': 'unknown',
            'confidence': 'low',
            'label': 'Causa desconocida',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': ['Sin datos de acceso UNC para clasificar.'],
        }

    accessible = access.get('accessible')
    error_raw = access.get('error_msg') or ''
    err = error_raw.lower()

    # --- Access succeeded ---
    if accessible is True:
        return {
            'cause': 'accessible',
            'confidence': 'high',
            'label': 'Acceso exitoso',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': [f"El recurso es accesible ({access.get('item_count', '?')} elemento(s))"],
        }

    # --- Access failed: classify by error content + config ---

    # 1. Host unreachable (no TCP 445)
    if reach.get('ping') is False and reach.get('tcp445') is False:
        return {
            'cause': 'host_unreachable',
            'confidence': 'high',
            'label': 'Servidor no alcanzable',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': ['Ping y TCP 445 fallaron.'],
        }

    if reach.get('tcp445') is False:
        return {
            'cause': 'tcp_445_blocked',
            'confidence': 'high',
            'label': 'Puerto TCP 445 bloqueado',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': ['Ping OK pero TCP 445 no alcanzable. Revise firewall intermedio.'],
        }

    # 2. SMB signing mismatch (primary confirmed incident pattern)
    has_signing_phrase = any(p in err for p in _SIGNING_PHRASES)
    require_signing = config.get('RequireSecuritySignature')

    if require_signing is True and (has_signing_phrase or reach.get('tcp445') is not False):
        details = ['RequireSecuritySignature = True en este cliente.']
        if has_signing_phrase:
            details.append(f'Error de firma detectado: {error_raw[:200]}')
        if not has_signing_phrase:
            details.append(
                'El servidor puede no requerir firma SMB. '
                'Deshabilitar RequireSecuritySignature es la corrección principal.'
            )
        return {
            'cause': 'smb_signing_mismatch',
            'confidence': 'high' if has_signing_phrase else 'medium',
            'label': 'Incompatibilidad de firma SMB',
            'recommended_action': 'smb.disable_require_signing',
            'risk_level': 'RISKY',
            'details': details,
        }

    if has_signing_phrase:
        return {
            'cause': 'smb_signing_mismatch',
            'confidence': 'medium',
            'label': 'Incompatibilidad de firma SMB (error detectado)',
            'recommended_action': 'smb.disable_require_signing',
            'risk_level': 'RISKY',
            'details': [f'Error: {error_raw[:200]}'],
        }

    # 3. Guest access blocked
    if any(p in err for p in _GUEST_PHRASES):
        return {
            'cause': 'guest_access_blocked',
            'confidence': 'high',
            'label': 'Acceso de invitado bloqueado',
            'recommended_action': 'smb.allow_insecure_guest',
            'risk_level': 'DESTRUCTIVE',
            'details': [
                f'Error: {error_raw[:200]}',
                'ADVERTENCIA: habilitar acceso de invitado es un riesgo de seguridad.',
            ],
        }

    # 4. Access denied / credentials
    if any(p in err for p in _ACCESS_DENIED_PHRASES):
        return {
            'cause': 'access_denied_credentials',
            'confidence': 'high',
            'label': 'Acceso denegado / credenciales',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': [
                f'Error: {error_raw[:200]}',
                'Verifique credenciales, permisos NTFS y permisos del recurso compartido.',
            ],
        }

    # 5. Share / path not found
    if any(p in err for p in _PATH_NOT_FOUND_PHRASES):
        return {
            'cause': 'share_not_found',
            'confidence': 'high',
            'label': 'Recurso compartido no encontrado',
            'recommended_action': None,
            'risk_level': 'INFO',
            'details': [
                f'Error: {error_raw[:200]}',
                'Verifique que el recurso compartido exista en el servidor (net share / Get-SmbShare).',
            ],
        }

    # 6. Fallback
    return {
        'cause': 'unknown',
        'confidence': 'low',
        'label': 'Causa desconocida',
        'recommended_action': None,
        'risk_level': 'INFO',
        'details': [
            error_raw[:200] if error_raw else 'Sin mensaje de error capturado.',
            'Revisión manual requerida.',
        ],
    }


# ---------------------------------------------------------------------------
# Full diagnosis orchestrator (read-only, runs all sub-queries in sequence)
# ---------------------------------------------------------------------------

def run_full_smb_diagnosis(host: str = '', unc_path: str = '') -> dict:
    """
    Orchestrate all read-only diagnostic sub-queries and classify the result.

    Runs: check_smb_services → get_smb_client_config → test_host_reachability
          → test_unc_access → classify_smb_issue.

    If unc_path is provided without host, the server is extracted from the UNC path
    and reachability is tested automatically.

    Returns:
        status: 'success' | 'error'
        host, unc_path: inputs (validated)
        findings: {services, client_config, reachability, unc_access}
        classification: from classify_smb_issue()
        query_errors: list of non-fatal sub-query errors
        timestamp: ISO format
    """
    findings = {}
    query_errors = []

    # SMB services
    svc = check_smb_services()
    if svc['status'] == 'success':
        findings['services'] = svc['services']
    else:
        query_errors.append(f"services: {svc.get('message', 'error')}")
        findings['services'] = {}

    # SMB client config
    cfg = get_smb_client_config()
    if cfg['status'] == 'success':
        findings['client_config'] = cfg['config']
    else:
        query_errors.append(f"client_config: {cfg.get('message', 'error')}")
        findings['client_config'] = {}

    # Resolve host from UNC path if not provided separately
    _host = host.strip() if host else ''
    _unc = unc_path.strip() if unc_path else ''

    if not _host and _unc and _is_safe_unc_path(_unc):
        _host = _extract_server(_unc)

    # Reachability
    if _host and _is_safe_host(_host):
        reach = test_host_reachability(_host)
        if reach['status'] == 'success':
            findings['reachability'] = reach['reachability']
        else:
            query_errors.append(f"reachability: {reach.get('message', 'error')}")
            findings['reachability'] = {}
    elif _host:
        query_errors.append(f"reachability: host no válido — {_host!r}")

    # UNC access
    if _unc and _is_safe_unc_path(_unc):
        access = test_unc_access(_unc)
        if access['status'] == 'success':
            findings['unc_access'] = access['access']
        else:
            query_errors.append(f"unc_access: {access.get('message', 'error')}")
            findings['unc_access'] = {}
    elif _unc:
        query_errors.append(f"unc_access: ruta UNC no válida — {_unc!r}")

    classification = classify_smb_issue(findings)

    return {
        'status': 'success',
        'host': _host,
        'unc_path': _unc,
        'findings': findings,
        'classification': classification,
        'query_errors': query_errors,
        'timestamp': datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Layer 3 — Safe remediations (all return CommandResult → go through governance)
# ---------------------------------------------------------------------------

def map_drive(drive_letter: str, unc_path: str) -> CommandResult:
    """
    Map a network share to a drive letter using net use.

    drive_letter: single letter A-Z (validated)
    unc_path: must pass _is_safe_unc_path validation

    Persists across reboots (/persistent:yes).
    """
    if not _is_safe_drive_letter(drive_letter):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Letra de unidad no válida: {drive_letter!r}',
        )
    if not _is_safe_unc_path(unc_path):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Ruta UNC no válida: {unc_path!r}',
        )

    letter = drive_letter.upper()
    return run_powershell(
        f"net use {letter}: '{unc_path}' /persistent:yes 2>&1",
        timeout=30,
        description=f'Map {letter}: to {unc_path}',
    )


def clear_smb_sessions() -> CommandResult:
    """
    Remove all mapped network drives and clear SMB session cache.

    Equivalent to: net use * /delete /y
    Disconnects all network drives on this machine.
    """
    return run_powershell(
        'net use * /delete /y 2>&1; Write-Output "SMB sessions cleared."',
        timeout=30,
        description='Clear all SMB sessions and mapped drives',
    )


def disable_require_signing() -> CommandResult:
    """
    Disable the mandatory SMB signing requirement on this client.

    This is the primary fix for the confirmed incident pattern:
      "You cannot access this shared folder because your computer is
       configured to require SMB signing"

    Sets RequireSecuritySignature = False.
    Preserves EnableSecuritySignature = True (signing is still offered and
    accepted when the server supports or requires it; only the local
    mandatory enforcement is removed).

    RISKY class: requires admin and confirmation.
    No reboot required, but a LanmanWorkstation service restart may be needed
    for the change to apply to existing sessions.
    """
    return run_powershell(
        'Set-SmbClientConfiguration -RequireSecuritySignature $false -Force;'
        '$c=Get-SmbClientConfiguration;'
        'Write-Output ("RequireSecuritySignature: " + $c.RequireSecuritySignature);'
        'Write-Output ("EnableSecuritySignature:  " + $c.EnableSecuritySignature)',
        requires_admin=True,
        timeout=30,
        description='Disable mandatory SMB signing requirement (RequireSecuritySignature=False)',
    )


def restart_lanman_workstation() -> CommandResult:
    """
    Restart the LanmanWorkstation (SMB client redirector) service.

    Required after changing SMB client configuration for the change to take
    effect on existing sessions. Briefly drops all active SMB connections.

    RISKY class: requires admin and confirmation.
    """
    return run_powershell(
        'Restart-Service LanmanWorkstation -Force;'
        '$s=Get-Service LanmanWorkstation;'
        'Write-Output ("LanmanWorkstation: " + $s.Status.ToString())',
        requires_admin=True,
        timeout=30,
        description='Restart LanmanWorkstation (SMB client) service',
    )


def allow_insecure_guest() -> CommandResult:
    """
    Enable insecure guest logons via Group Policy registry key.

    WARNING: This is NOT the default/recommended fix.
    The correct fix for the confirmed incident pattern is disable_require_signing().
    This action is provided only for legacy environments where the server
    genuinely requires unauthenticated guest access.

    Sets:
        HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\LanmanWorkstation
        AllowInsecureGuestAuth = DWORD 1

    Restarts LanmanWorkstation to apply immediately.

    DESTRUCTIVE class: requires admin, confirmation, and EXPERT mode.

    Limitation: Group Policy refresh may overwrite this registry value.
    """
    ps = (
        "$path='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\LanmanWorkstation';"
        "if(-not(Test-Path $path)){New-Item $path -Force|Out-Null};"
        "Set-ItemProperty $path AllowInsecureGuestAuth 1 -Type DWORD -Force;"
        "Restart-Service LanmanWorkstation -Force -EA SilentlyContinue;"
        "$v=(Get-ItemProperty $path -Name AllowInsecureGuestAuth -EA SilentlyContinue)"
        ".AllowInsecureGuestAuth;"
        "Write-Output ('AllowInsecureGuestAuth = ' + $v);"
        "Write-Output 'LanmanWorkstation reiniciado.'"
    )
    return run_powershell(
        ps,
        requires_admin=True,
        timeout=30,
        description='Enable insecure guest logons (AllowInsecureGuestAuth=1) — legacy only',
    )
