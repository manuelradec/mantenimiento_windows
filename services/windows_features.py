"""
Windows Features — Phase 4 Wave 2: Shared-folder guided troubleshooting.

Provides:
  - Comprehensive shared-folder diagnostic (read-only)
  - TCP 445 connectivity test to a given server (read-only)
  - Explorer launcher for a validated UNC path (GUI launcher, no state change)

Scope for this phase:
  - Shared-folder diagnostic composite (services, SMB config, shares, connections,
    mapped drives, port 445 listener state, network discovery firewall state)
  - UNC path input validation and targeted connectivity test
  - Explorer launcher so the technician can open the target path directly

NOT in scope for this phase:
  - SMB1/CIFS enablement
  - .NET 3.5 or .NET 4.8 feature enablement
  - Any legacy Windows Feature management

Environment limitations:
  - Get-SmbShare, Get-SmbConnection, Get-SmbServerConfiguration require
    Windows 8+ / Server 2012 R2+.  Wrapped in try/catch; absent on older OS
    surfaces as null/empty rather than an error.
  - TCP 445 test may time out on heavily firewalled paths (30s timeout).
  - open_network_path() launches Explorer detached — the function returns
    immediately; no way to confirm Explorer rendered the share successfully.
  - UNC regex is intentionally conservative (ASCII alphanumeric + common
    separators).  Unicode hostnames and share names with special characters
    will be rejected at the validation layer.
"""
import re
import logging

from services.command_runner import (
    run_powershell, run_powershell_json, CommandStatus, CommandResult
)

logger = logging.getLogger('cleancpu.windows_features')


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

# Conservative UNC path pattern.
# Allows: \\server\share  \\server\share\subfolder  \\192.168.1.1\share
# Disallows: quotes, backticks, dollar signs, semicolons, pipes, etc.
_UNC_RE = re.compile(
    r'^\\\\[a-zA-Z0-9._-]{1,253}\\[a-zA-Z0-9 ._-]{1,80}'
    r'(\\[a-zA-Z0-9 ._-]{1,260})*$'
)
_UNC_FORBIDDEN = set('"\'`$;|&<>()\n\r')


def _is_safe_unc_path(path: str) -> bool:
    """Return True if path is a safe, well-formed UNC path for PS interpolation."""
    if not isinstance(path, str):
        return False
    if any(c in _UNC_FORBIDDEN for c in path):
        return False
    return bool(_UNC_RE.match(path))


def _extract_server(unc_path: str) -> str:
    """Extract the server/host component from a validated UNC path."""
    # \\server\share → 'server'
    parts = unc_path.lstrip('\\').split('\\')
    return parts[0] if parts else ''


# ---------------------------------------------------------------------------
# Shared-folder diagnostic (read-only composite query)
#
# Single PS script to minimise round-trips.  Each section is wrapped in
# try/catch so a missing cmdlet (e.g. Get-SmbShare on a stripped OS) does
# not abort the whole query.
# ---------------------------------------------------------------------------

_DIAG_QUERY_PS = (
    # Build result object
    "$r=[PSCustomObject]@{"
    "smb_server_svc=$null;smb_server_start=$null;"
    "smb_client_svc=$null;smb_client_start=$null;"
    "smb1=$null;smb2=$null;"
    "port445=$null;nd_enabled=$null;"
    "shares=@();connections=@();mapped_drives=@()"
    "};"

    # LanmanServer (File & Printer Sharing server)
    "$s=Get-Service LanmanServer -EA SilentlyContinue;"
    "if($s){$r.smb_server_svc=$s.Status.ToString();"
    "$r.smb_server_start=$s.StartType.ToString()};"

    # LanmanWorkstation (SMB client / redirector)
    "$s=Get-Service LanmanWorkstation -EA SilentlyContinue;"
    "if($s){$r.smb_client_svc=$s.Status.ToString();"
    "$r.smb_client_start=$s.StartType.ToString()};"

    # SMB server configuration (SMB1/SMB2)
    "try{"
    "$sc=Get-SmbServerConfiguration -EA Stop;"
    "$r.smb1=$sc.EnableSMB1Protocol;"
    "$r.smb2=$sc.EnableSMB2Protocol"
    "}catch{};"

    # Non-administrative shares (exclude default admin shares: ADMIN$, C$, IPC$)
    "try{"
    "$r.shares=@(Get-SmbShare -EA Stop"
    "|Where-Object{$_.Name -notmatch '^[A-Z]\\$$|^ADMIN\\$$|^IPC\\$$'}"
    "|Select-Object Name,Path,ShareState,Description"
    ")}catch{};"

    # Active SMB connections (what this machine has open to other servers)
    "try{"
    "$r.connections=@(Get-SmbConnection -EA Stop"
    "|Select-Object ServerName,ShareName,Dialect,NumOpens"
    ")}catch{};"

    # TCP 445 listening state (is this machine serving SMB?)
    "$r.port445=[bool](Get-NetTCPConnection -LocalPort 445"
    " -State Listen -EA SilentlyContinue);"

    # Network Discovery firewall group (locale-independent resource string)
    "$nd=Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752' -EA SilentlyContinue;"
    "if($nd){"
    "$r.nd_enabled=("
    "$nd|Where-Object{$_.Enabled -eq 'True'}|Measure-Object).Count -gt 0"
    "};"

    # Mapped network drives
    "try{"
    "$r.mapped_drives=@(Get-PSDrive -PSProvider FileSystem -EA SilentlyContinue"
    "|Where-Object{$_.DisplayRoot -like '\\\\*'}"
    "|Select-Object Name,DisplayRoot"
    ")}catch{};"

    "$r|ConvertTo-Json -Compress -Depth 4"
)


def run_shared_folder_diagnostics() -> dict:
    """
    Run a comprehensive shared-folder diagnostic query.

    Returns structured dict with:
        status: 'success' | 'error'
        diag: dict with all collected fields
    """
    result = run_powershell_json(
        _DIAG_QUERY_PS,
        description='Shared-folder diagnostic composite',
    )

    raw = result.details.get('data') if result.details else None
    if isinstance(raw, list):
        raw = raw[0] if raw else None

    if result.is_error or not isinstance(raw, dict):
        return {
            'status': 'error',
            'message': result.error or 'Error al ejecutar diagnóstico de carpetas compartidas',
            'diag': {},
        }

    # Normalise list fields (single-item PS arrays come back as dicts)
    for list_key in ('shares', 'connections', 'mapped_drives'):
        val = raw.get(list_key)
        if isinstance(val, dict):
            raw[list_key] = [val]
        elif not isinstance(val, list):
            raw[list_key] = []

    return {'status': 'success', 'diag': raw}


# ---------------------------------------------------------------------------
# UNC connectivity test (read-only)
#
# Extracts the server name from a validated UNC path and tests TCP 445.
# ---------------------------------------------------------------------------

def test_unc_connectivity(unc_path: str) -> CommandResult:
    """
    Test TCP 445 connectivity to the server in a UNC path.

    unc_path: e.g. \\\\server\\share or \\\\192.168.1.10\\data
    The server name is extracted and Test-NetConnection -Port 445 is run.
    """
    if not _is_safe_unc_path(unc_path):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Ruta UNC no válida o contiene caracteres no permitidos: {unc_path!r}',
        )

    server = _extract_server(unc_path)
    if not server:
        return CommandResult(
            status=CommandStatus.ERROR,
            error='No se pudo extraer el nombre del servidor de la ruta UNC.',
        )

    return run_powershell(
        f"Test-NetConnection -ComputerName '{server}' -Port 445",
        timeout=30,
        description=f'Test TCP 445 to {server}',
    )


# ---------------------------------------------------------------------------
# UNC path launcher (GUI launcher, no state change)
#
# Opens a validated UNC path in Windows Explorer via Start-Process.
# Returns immediately — Explorer runs detached.
# ---------------------------------------------------------------------------

def open_network_path(unc_path: str) -> CommandResult:
    """
    Open a validated UNC path in Windows Explorer.

    Launches detached — returns immediately before Explorer renders.
    No state is written to disk or registry.
    """
    if not _is_safe_unc_path(unc_path):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Ruta UNC no válida o contiene caracteres no permitidos: {unc_path!r}',
        )

    return run_powershell(
        f'Start-Process explorer.exe -ArgumentList "{unc_path}"',
        timeout=10,
        description=f'Open {unc_path} in Explorer',
    )


# ---------------------------------------------------------------------------
# Optional Windows Features — Phase 5 Wave 2
#
# Detection and enablement of:
#   - .NET Framework 3.5  (FeatureName: NetFx3)
#   - .NET Framework 4.8 Advanced Services  (FeatureName: NetFx4-AdvSrvs)
#   - SMB1/CIFS  (FeatureName: SMB1Protocol) — LEGACY / HIGH-RISK
#
# All enablement calls use -NoRestart: the feature is staged but inactive
# until the operator reboots.  All require admin and a healthy CBS service.
#
# Environment limitations:
#   - .NET 3.5 may need Windows media or WSUS for source files (-All handles
#     automatic resolution; DISM returns 0x800f0950 if unavailable offline).
#   - NetFx4-AdvSrvs may be absent on LTSC/IoT editions → state = null.
#   - SMB1 is disabled-by-default on Windows 10 1709+ / Windows 11.
#     Enabling it is a deliberate security downgrade; DESTRUCTIVE risk class.
# ---------------------------------------------------------------------------

_OPTIONAL_FEATURES_PS = (
    "$r=[PSCustomObject]@{"
    "dotnet35=$null;dotnet48_adv=$null;smb1_feature=$null;smb1_runtime=$null"
    "};"
    "try{$f=Get-WindowsOptionalFeature -Online -FeatureName NetFx3 -EA Stop;"
    "$r.dotnet35=$f.State.ToString()}catch{};"
    "try{$f=Get-WindowsOptionalFeature -Online -FeatureName NetFx4-AdvSrvs -EA Stop;"
    "$r.dotnet48_adv=$f.State.ToString()}catch{};"
    "try{$f=Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -EA Stop;"
    "$r.smb1_feature=$f.State.ToString()}catch{};"
    "try{$sc=Get-SmbServerConfiguration -EA Stop;"
    "$r.smb1_runtime=$sc.EnableSMB1Protocol}catch{};"
    "$r|ConvertTo-Json -Compress"
)


def get_optional_features_status() -> dict:
    """
    Return current state of optional Windows features.

    State values from Get-WindowsOptionalFeature:
        'Enabled'         — installed and active
        'Disabled'        — not installed
        'EnablePending'   — scheduled to enable on next reboot
        'DisablePending'  — scheduled to disable on next reboot
        null              — feature not present on this OS edition
    """
    result = run_powershell_json(
        _OPTIONAL_FEATURES_PS,
        description='Query optional Windows features state',
    )

    raw = result.details.get('data') if result.details else None
    if isinstance(raw, list):
        raw = raw[0] if raw else None

    if result.is_error or not isinstance(raw, dict):
        return {
            'status': 'error',
            'message': result.error or 'Error al consultar características de Windows',
            'features': {},
        }

    return {
        'status': 'success',
        'features': {
            'dotnet35': raw.get('dotnet35'),
            'dotnet48_adv': raw.get('dotnet48_adv'),
            'smb1_feature': raw.get('smb1_feature'),
            'smb1_runtime': raw.get('smb1_runtime'),
        },
    }


def enable_dotnet35() -> CommandResult:
    """
    Enable .NET Framework 3.5 via DISM.

    Uses -All to enable parent features automatically.
    May require internet/WSUS if source files are not cached locally.
    Reboot required to activate.
    """
    return run_powershell(
        'Enable-WindowsOptionalFeature -Online -FeatureName NetFx3'
        ' -All -NoRestart',
        requires_admin=True,
        timeout=300,
        description='Enable .NET Framework 3.5 via DISM',
    )


def enable_dotnet48_adv() -> CommandResult:
    """
    Enable .NET Framework 4.8 Advanced Services via DISM.

    Enables WCF and related sub-features (-All).
    May not be available on LTSC/IoT editions.
    Reboot required to activate.
    """
    return run_powershell(
        'Enable-WindowsOptionalFeature -Online -FeatureName NetFx4-AdvSrvs'
        ' -All -NoRestart',
        requires_admin=True,
        timeout=300,
        description='Enable .NET Framework 4.8 Advanced Services via DISM',
    )


def enable_smb1() -> CommandResult:
    """
    Enable SMB1/CIFS file-sharing protocol via DISM.

    WARNING: SMB1 is a deprecated protocol with critical known vulnerabilities
    (CVE-2017-0144 EternalBlue / WannaCry).  Only enable when explicitly
    required for access to legacy resources that cannot be upgraded.

    Reboot required to activate.  DESTRUCTIVE risk class.
    """
    return run_powershell(
        'Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol'
        ' -NoRestart',
        requires_admin=True,
        timeout=120,
        description='Enable SMB1 protocol via DISM (legacy/insecure)',
    )
