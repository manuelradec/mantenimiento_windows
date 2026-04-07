"""
Sharing and NetBIOS tools — Phase 3 Wave 2.

Detects and manages:
  - Sharing-related Windows settings (Network Discovery, File & Printer Sharing,
    SMB1/SMB2 status, Public folder sharing) — read-only diagnostic panel.
  - Network Discovery firewall group enable/disable — managed action.
  - NetBIOS over TCP/IP per-adapter state — managed action.

Detection approach:
  - Network Discovery: Get-NetFirewallRule with the locale-independent internal
    group resource string '@FirewallAPI.dll,-32752'. This works regardless of
    the OS display language (Spanish, English, etc.).
  - File & Printer Sharing: LanmanServer service state as a proxy.
  - SMB settings: Get-SmbServerConfiguration (Windows 8+ / Server 2012+).
  - Public folder: whether any SmbShare path contains Users\\Public.
  - NetBIOS per adapter: Win32_NetworkAdapterConfiguration.TcpipNetbiosOptions.

Limitations stated clearly:
  - Group Policy can override local firewall settings on domain-joined machines.
    Changes made here will not persist if GPO re-applies.
  - Public folder and password-protected sharing are shown read-only; no change
    action is provided (those settings involve too many sub-components to manage
    safely as atomic actions).
  - NetBIOS mode 0 (Default via DHCP) only applies when the adapter uses DHCP;
    the value is stored but ignored by the OS on static-IP adapters.
  - Get-WmiObject is used for SetTcpipNetbios (WMI method unavailable via
    Get-CimInstance). PowerShell 5.1 (default on Windows 10/11) supports it.
"""
import logging
import re

from services.command_runner import (
    run_powershell, run_powershell_json, CommandStatus, CommandResult
)

logger = logging.getLogger('cleancpu.sharing')

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_ADAPTER_INDEX_MAX = 9999
_NETBIOS_MODES = frozenset({0, 1, 2})
_NETBIOS_MODE_LABELS = {
    0: 'predeterminado (DHCP)',
    1: 'habilitado',
    2: 'deshabilitado',
}


def _is_safe_adapter_index(value) -> bool:
    """Return True if value is a non-negative integer within safe range."""
    try:
        idx = int(value)
        return 0 <= idx <= _ADAPTER_INDEX_MAX
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Sharing settings detection (read-only)
#
# Single PS script builds a PSCustomObject and serialises it to JSON.
# '@FirewallAPI.dll,-32752' is the locale-independent internal resource ID
# for the Network Discovery firewall rule group (Windows 8+/Server 2012+).
# ---------------------------------------------------------------------------

_SHARING_QUERY_PS = (
    "$r=[PSCustomObject]@{"
    "nd_total=0;nd_enabled=0;nd_svc=$null;nd_svc_start=$null;"
    "fp_svc=$null;fp_svc_start=$null;smb1=$null;smb2=$null;public_folder=$false"
    "};"
    "$nd=Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752'"
    " -ErrorAction SilentlyContinue;"
    "if($nd){"
    "$r.nd_total=($nd|Measure-Object).Count;"
    "$r.nd_enabled=($nd|Where-Object{$_.Enabled -eq 'True'}|Measure-Object).Count"
    "};"
    "$s=Get-Service fdphost -ErrorAction SilentlyContinue;"
    "if($s){$r.nd_svc=$s.Status.ToString();$r.nd_svc_start=$s.StartType.ToString()};"
    "$s=Get-Service LanmanServer -ErrorAction SilentlyContinue;"
    "if($s){$r.fp_svc=$s.Status.ToString();$r.fp_svc_start=$s.StartType.ToString()};"
    "try{"
    "$sc=Get-SmbServerConfiguration -ErrorAction Stop;"
    "$r.smb1=$sc.EnableSMB1Protocol;$r.smb2=$sc.EnableSMB2Protocol"
    "}catch{};"
    "$r.public_folder=[bool](Get-SmbShare -ErrorAction SilentlyContinue"
    "|Where-Object{$_.Path -like '*\\Users\\Public*' -or $_.Name -eq 'Users'});"
    "$r|ConvertTo-Json -Compress"
)


def get_sharing_settings() -> dict:
    """
    Read current sharing-related settings.

    Returns:
        status: 'success' | 'error'
        settings: dict with keys:
            network_discovery.enabled (bool | None) — derived from firewall rule count
            network_discovery.source ('firewall' | 'unknown')
            network_discovery.nd_total / nd_enabled (int) — raw rule counts
            network_discovery.service_state (str | None) — fdphost state (reference)
            file_printer_sharing.enabled (bool | None) — LanmanServer running
            file_printer_sharing.service_state (str | None)
            file_printer_sharing.start_type (str | None)
            smb.smb1_enabled (bool | None)
            smb.smb2_enabled (bool | None)
            public_folder.detected (bool)
    """
    result = run_powershell_json(
        _SHARING_QUERY_PS,
        description='Query sharing settings',
    )

    raw = result.details.get('data') if result.details else None
    if isinstance(raw, list):
        raw = raw[0] if raw else None

    if result.is_error or not isinstance(raw, dict):
        return {
            'status': 'error',
            'message': result.error or 'Error al consultar configuración de uso compartido',
            'settings': {},
        }

    nd_total = int(raw.get('nd_total') or 0)
    nd_enabled = int(raw.get('nd_enabled') or 0)

    # Network discovery is "on" when at least one rule in the group is enabled.
    # If no rules found (nd_total == 0), the state is truly unknown.
    if nd_total > 0:
        nd_on = nd_enabled > 0
        nd_source = 'firewall'
    else:
        nd_on = None
        nd_source = 'unknown'

    fp_svc = raw.get('fp_svc')

    return {
        'status': 'success',
        'settings': {
            'network_discovery': {
                'enabled': nd_on,
                'source': nd_source,
                'nd_total': nd_total,
                'nd_enabled': nd_enabled,
                'service_state': raw.get('nd_svc'),
            },
            'file_printer_sharing': {
                'enabled': fp_svc == 'Running' if fp_svc is not None else None,
                'service_state': fp_svc,
                'start_type': raw.get('fp_svc_start'),
            },
            'smb': {
                'smb1_enabled': raw.get('smb1'),
                'smb2_enabled': raw.get('smb2'),
            },
            'public_folder': {
                'detected': bool(raw.get('public_folder', False)),
            },
        },
    }


# ---------------------------------------------------------------------------
# NetBIOS per-adapter detection (read-only)
#
# Uses Get-CimInstance for detection (modern, no deprecated warning).
# TcpipNetbiosOptions values:
#   0 = DefaultViaDhcp (use the NetBIOS option from the DHCP server)
#   1 = EnableNetbiosOverTcpip
#   2 = DisableNetbiosOverTcpip
# ---------------------------------------------------------------------------

_NETBIOS_QUERY_PS = (
    "Get-CimInstance Win32_NetworkAdapterConfiguration"
    " -Filter 'IPEnabled = TRUE' |"
    " Select-Object Description,Index,TcpipNetbiosOptions,IPAddress |"
    " ConvertTo-Json -Compress -Depth 3"
)


def get_netbios_adapters() -> dict:
    """
    Return IP-enabled network adapters with their NetBIOS mode.

    Returns:
        status: 'success' | 'error'
        adapters: list of dicts with keys:
            description, index, netbios_options (0/1/2),
            netbios_label, ip_addresses (list[str])
    """
    result = run_powershell_json(
        _NETBIOS_QUERY_PS,
        description='Query NetBIOS per-adapter settings',
    )

    raw = result.details.get('data') if result.details else None
    if isinstance(raw, dict):
        raw = [raw]

    if result.is_error or not isinstance(raw, list):
        return {
            'status': 'error',
            'message': result.error or 'Error al consultar configuración NetBIOS',
            'adapters': [],
        }

    adapters = []
    for item in raw:
        opts = item.get('TcpipNetbiosOptions')
        if opts is None:
            opts_int = None
            label = 'Desconocido'
        else:
            opts_int = int(opts)
            label = _NETBIOS_MODE_LABELS.get(opts_int, f'Valor {opts_int}')

        # IPAddress is a list in WMI (may be multiple IPv4 + IPv6 addresses)
        ip_raw = item.get('IPAddress') or []
        if isinstance(ip_raw, str):
            ip_raw = [ip_raw]
        # Keep only IPv4 for display
        ip_v4 = [ip for ip in ip_raw if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip)]

        adapters.append({
            'description': item.get('Description', '') or '',
            'index': item.get('Index'),
            'netbios_options': opts_int,
            'netbios_label': label,
            'ip_addresses': ip_v4,
        })

    return {'status': 'success', 'adapters': adapters}


# ---------------------------------------------------------------------------
# Network Discovery enable / disable
#
# Uses Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752' — the internal
# resource string is locale-independent (unlike netsh group= which requires
# the localised group name).  Requires admin.
# ---------------------------------------------------------------------------

def enable_network_discovery() -> CommandResult:
    """Enable the Network Discovery firewall rule group. Requires admin."""
    return run_powershell(
        "Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752'"
        " | Enable-NetFirewallRule",
        requires_admin=True,
        description='Enable Network Discovery firewall group',
    )


def disable_network_discovery() -> CommandResult:
    """Disable the Network Discovery firewall rule group. Requires admin."""
    return run_powershell(
        "Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752'"
        " | Disable-NetFirewallRule",
        requires_admin=True,
        description='Disable Network Discovery firewall group',
    )


# ---------------------------------------------------------------------------
# NetBIOS per-adapter change
#
# Uses Get-WmiObject (not Get-CimInstance) because SetTcpipNetbios() is a
# WMI method not available via Get-CimInstance without Invoke-CimMethod.
# PowerShell 5.1 (default on Windows 10/11) supports Get-WmiObject.
# ---------------------------------------------------------------------------

def set_netbios_mode(adapter_index, mode) -> CommandResult:
    """
    Set NetBIOS over TCP/IP mode for an IP-enabled adapter by WMI index.

    adapter_index: integer adapter index from Win32_NetworkAdapterConfiguration
    mode:
        0 = DefaultViaDhcp (use DHCP server option; ignored if adapter is static)
        1 = EnableNetbiosOverTcpip
        2 = DisableNetbiosOverTcpip

    Requires admin.
    """
    if not _is_safe_adapter_index(adapter_index):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Índice de adaptador no válido: {adapter_index!r}',
        )

    try:
        mode_int = int(mode)
    except (TypeError, ValueError):
        mode_int = -1

    if mode_int not in _NETBIOS_MODES:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Modo NetBIOS no válido: {mode!r}. Debe ser 0, 1 o 2.',
        )

    idx = int(adapter_index)
    ps = (
        f"$adp = Get-WmiObject Win32_NetworkAdapterConfiguration"
        f" | Where-Object {{$_.Index -eq {idx}}};"
        f" if ($adp) {{"
        f"  $res = $adp.SetTcpipNetbios({mode_int});"
        f"  if ($res.ReturnValue -ne 0) {{"
        f"   Write-Error \"SetTcpipNetbios devolvio: $($res.ReturnValue)\""
        f"  }} else {{"
        f"   Write-Host 'NetBIOS actualizado correctamente'"
        f"  }}"
        f" }} else {{"
        f"  Write-Error 'No se encontro el adaptador con indice {idx}'"
        f" }}"
    )
    return run_powershell(
        ps,
        requires_admin=True,
        description=(
            f'Set NetBIOS to {_NETBIOS_MODE_LABELS[mode_int]}'
            f' on adapter index {idx}'
        ),
    )
