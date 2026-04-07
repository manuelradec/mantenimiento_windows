"""
Network and connectivity module.

Handles: DNS flush, IP reset, network stack, TCP settings, connectivity tests,
SMB sessions, network adapters, proxy settings, service status.
"""
import re
import ipaddress
import logging
from typing import Optional

from services.command_runner import (
    run_cmd, run_powershell, run_powershell_json, CommandStatus, CommandResult
)

logger = logging.getLogger('maintenance.network')

# RFC 952 / 1123 hostname pattern — compiled once at module load
_HOSTNAME_RE = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)

# ---------------------------------------------------------------------------
# RADEC target catalog — predefined connectivity test endpoints.
# Fields: label (display name), host (IP or FQDN), default_port (int or None).
# default_port=None → ICMP/ping-style test (Test-NetConnection without -Port).
# ---------------------------------------------------------------------------
RADEC_TARGETS = [
    # Infrastructure / internet
    {'label': 'Correo (mail.radec.com.mx)', 'host': 'mail.radec.com.mx', 'default_port': 25},
    {'label': 'DNS pública (Google)', 'host': '8.8.8.8', 'default_port': 53},
    {'label': 'Internet (google.com)', 'host': 'google.com', 'default_port': 443},
    {'label': 'Intranet', 'host': '192.168.103.25', 'default_port': None},
    # SAP / servers
    {'label': 'SAP', 'host': '192.168.198.14', 'default_port': None},
    {'label': 'SAP DB', 'host': '192.168.198.14', 'default_port': None},
    {'label': 'SAP Aplicativo 1', 'host': '192.168.198.15', 'default_port': None},
    {'label': 'SAP Aplicativo 2', 'host': '192.168.198.16', 'default_port': None},
    {'label': 'Sygnology CLJ', 'host': '192.168.122.215', 'default_port': None},
    {'label': 'Sygnology Matriz (1)', 'host': '192.168.100.116', 'default_port': None},
    {'label': 'Sygnology Matriz (2)', 'host': '192.168.100.8', 'default_port': None},
    {'label': 'OCS Inventory NG', 'host': '192.168.103.72', 'default_port': 80},
    # Sucursales
    {'label': '16 de Septiembre', 'host': '192.168.102.17', 'default_port': None},
    {'label': 'QAS', 'host': '192.168.103.207', 'default_port': None},
    {'label': 'CDG1', 'host': '192.168.103.17', 'default_port': None},
    {'label': 'Central', 'host': '192.168.103.70', 'default_port': None},
    {'label': 'Refacturación', 'host': '192.168.103.90', 'default_port': None},
    {'label': 'Laureles', 'host': '192.168.104.17', 'default_port': None},
    {'label': 'Peralvillo', 'host': '192.168.105.17', 'default_port': None},
    {'label': 'Ejército', 'host': '192.168.106.16', 'default_port': None},
    {'label': 'Monterrey', 'host': '192.168.107.17', 'default_port': None},
    {'label': 'Juárez', 'host': '192.168.108.17', 'default_port': None},
    {'label': 'Bulgaria', 'host': '192.168.109.17', 'default_port': None},
    {'label': 'Villahermosa', 'host': '192.168.110.17', 'default_port': None},
    {'label': 'León', 'host': '192.168.111.17', 'default_port': None},
    {'label': 'Tijuana CR', 'host': '192.168.112.17', 'default_port': None},
    {'label': 'Tultitlán', 'host': '192.168.113.17', 'default_port': None},
    {'label': 'Chihuahua', 'host': '192.168.115.17', 'default_port': None},
    {'label': 'Tijuana CN', 'host': '192.168.116.17', 'default_port': None},
    {'label': 'Mexicali', 'host': '192.168.117.17', 'default_port': None},
    {'label': 'Cancún', 'host': '192.168.118.17', 'default_port': None},
    {'label': 'Veracruz', 'host': '192.168.119.17', 'default_port': None},
    {'label': 'Mérida', 'host': '192.168.120.17', 'default_port': None},
    {'label': 'Puebla', 'host': '192.168.121.17', 'default_port': None},
    {'label': 'SLP', 'host': '192.168.124.17', 'default_port': None},
    {'label': 'Tecámac', 'host': '192.168.125.17', 'default_port': None},
    {'label': 'Querétaro', 'host': '192.168.126.17', 'default_port': None},
    {'label': 'Hermosillo', 'host': '192.168.127.17', 'default_port': None},
    {'label': 'Torreón', 'host': '192.168.128.17', 'default_port': None},
    {'label': 'Toluca', 'host': '192.168.129.17', 'default_port': None},
    {'label': 'Morelia', 'host': '192.168.130.17', 'default_port': None},
    {'label': 'Saltillo', 'host': '192.168.131.17', 'default_port': None},
    {'label': 'Reynosa', 'host': '192.168.132.17', 'default_port': None},
    {'label': 'Tuxtla', 'host': '192.168.133.17', 'default_port': None},
    {'label': 'Guadalupe', 'host': '192.168.134.17', 'default_port': None},
    {'label': 'Culiacán', 'host': '192.168.135.17', 'default_port': None},
    {'label': 'Tampico', 'host': '192.168.140.17', 'default_port': None},
    {'label': 'Acapulco', 'host': '192.168.141.17', 'default_port': None},
    {'label': 'Iztapalapa', 'host': '192.168.143.17', 'default_port': None},
]


def _validate_connection_params(host: str, port) -> Optional[str]:
    """
    Validate host and optional port for test_connectivity.

    port=None means host-only (ICMP) test — port validation is skipped.
    Returns an error message string if invalid, or None if valid.
    Separated from business logic so it can be tested independently.
    """
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # Not an IP — validate as RFC 1123 hostname
        if not _HOSTNAME_RE.match(host) or len(host) > 253:
            return 'Invalid host. Must be a valid IP address or hostname.'

    if port is None:
        return None  # Host-only test — no port needed

    try:
        port_int = int(port)
    except (ValueError, TypeError):
        return 'Invalid port. Must be an integer.'

    if not (1 <= port_int <= 65535):
        return 'Invalid port. Must be between 1 and 65535.'

    return None


def flush_dns():
    """Flush DNS resolver cache."""
    return run_cmd('ipconfig /flushdns', description='Flush DNS cache')


def release_ip():
    """Release current IP address. May cause temporary disconnection."""
    return run_cmd('ipconfig /release', description='Release IP address')


def renew_ip():
    """Renew IP address from DHCP."""
    return run_cmd('ipconfig /renew', timeout=30, description='Renew IP address')


def reset_ip_stack():
    """
    Reset TCP/IP stack. WARNING: May disconnect network.
    Reboot recommended after this operation.
    """
    return run_cmd(
        'netsh int ip reset',
        requires_admin=True,
        description='Reset TCP/IP stack',
    )


def reset_winsock():
    """Reset Winsock catalog. Reboot recommended after."""
    return run_cmd(
        'netsh winsock reset',
        requires_admin=True,
        description='Reset Winsock catalog',
    )


def show_tcp_global():
    """Show TCP global parameters (read-only diagnostic)."""
    return run_cmd(
        'netsh int tcp show global',
        description='Show TCP global settings',
    )


def set_autotuning_normal():
    """Set TCP autotuning to normal (recommended default)."""
    return run_cmd(
        'netsh int tcp set global autotuninglevel=normal',
        requires_admin=True,
        description='Set TCP autotuning to normal',
    )


def test_connectivity(host='8.8.8.8', port=443):
    """
    Test network connectivity to a specific host, optionally on a TCP port.

    port=None  → ICMP/ping-style test via Test-NetConnection (no -Port flag).
                 Reports PingSucceeded and RoundTripTime.
    port=<int> → TCP port reachability test via Test-NetConnection -Port.
                 Reports TcpTestSucceeded in addition to ping result.
    """
    host = str(host).strip()
    error = _validate_connection_params(host, port)
    if error:
        return CommandResult(status=CommandStatus.ERROR, error=error)

    if port is None:
        ps = f'Test-NetConnection -ComputerName {host} -InformationLevel Detailed'
        desc = f'Test connectivity (ICMP) to {host}'
    else:
        port = int(port)  # Safe after validation
        ps = f'Test-NetConnection -ComputerName {host} -Port {port}'
        desc = f'Test connectivity to {host}:{port}'

    return run_powershell(ps, timeout=30, description=desc)


def get_radec_targets():
    """Return the RADEC target catalog as a list of dicts."""
    return list(RADEC_TARGETS)  # Shallow copy — caller cannot mutate the constant


# ---------------------------------------------------------------------------
# Managed service startup mode switching — Phase 6.
# Strictly scoped to 7 network-discovery / file-sharing services.
# No other services can be targeted through these functions.
# ---------------------------------------------------------------------------

# Windows service name → Spanish display label
_MANAGED_SERVICES = {
    'fdphost': 'Function Discovery Provider Host',
    'FDResPub': 'Function Discovery Resource Publication',
    'SSDPSRV': 'SSDP Discovery',
    'upnphost': 'UPnP Device Host',
    'LanmanServer': 'Servidor',
    'LanmanWorkstation': 'Estación de trabajo',
    'Browser': 'Exploración de equipos',
}

# Services known to be deprecated / removed in modern Windows versions.
# Shown with an explanatory note rather than just "not found".
_DEPRECATED_SERVICES = {
    'Browser': (
        'El servicio "Exploración de equipos" (Computer Browser) fue eliminado '
        'en Windows 10 versión 1803 junto con SMBv1. '
        'Si no aparece, es el comportamiento esperado.'
    ),
}


def get_managed_services() -> dict:
    """
    Query the current state and startup type of the 7 managed services.

    Uses Get-CimInstance Win32_Service — compatible with PS 3+ / Win 8+.
    Services that do not exist on this machine are returned with exists=False.

    Returns:
        status: 'success' | 'error'
        services: list of dicts with keys:
            name, display_name, state, start_mode, exists, deprecated_note
    """
    # Build a WQL filter: Name='a' OR Name='b' OR ...
    wql_filter = ' OR '.join(f"Name='{n}'" for n in _MANAGED_SERVICES)

    result = run_powershell_json(
        f'Get-CimInstance Win32_Service -Filter "{wql_filter}" '
        '| Select-Object Name, DisplayName, State, StartMode '
        '| Sort-Object Name',
        description='Query managed network service states',
    )

    # Build a lookup from the PS result (handle single-dict vs list)
    raw = result.details.get('data') if result.details else None
    if isinstance(raw, dict):
        raw = [raw]
    found = {}
    for item in (raw if isinstance(raw, list) else []):
        svc_name = item.get('Name', '')
        if svc_name:
            found[svc_name] = item

    services = []
    for svc_name, display in _MANAGED_SERVICES.items():
        deprecated_note = _DEPRECATED_SERVICES.get(svc_name, '')
        if svc_name in found:
            item = found[svc_name]
            services.append({
                'name': svc_name,
                'display_name': item.get('DisplayName') or display,
                'state': item.get('State', ''),
                'start_mode': item.get('StartMode', ''),
                'exists': True,
                'deprecated_note': '',
            })
        else:
            services.append({
                'name': svc_name,
                'display_name': display,
                'state': '',
                'start_mode': '',
                'exists': False,
                'deprecated_note': deprecated_note,
            })

    if result.is_error and not found:
        return {
            'status': 'error',
            'message': f'Error al consultar servicios: {result.error or "desconocido"}',
            'services': services,
        }

    return {'status': 'success', 'services': services}


def set_service_startup(service_name: str, startup_type: str) -> CommandResult:
    """
    Change the startup type of one of the 7 managed services.

    service_name: must be an exact key in _MANAGED_SERVICES (enforced).
    startup_type: 'Automatic' or 'Manual' only (enforced).

    Requires admin (run_powershell with requires_admin=True).
    Returns a CommandResult; caller should check .is_error.
    """
    if service_name not in _MANAGED_SERVICES:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=(
                f'Servicio \'{service_name}\' no está en la lista de servicios '
                'gestionados. Solo se permiten los 7 servicios predefinidos.'
            ),
        )

    valid_types = {'Automatic', 'Manual'}
    if startup_type not in valid_types:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=(
                f'Tipo de inicio \'{startup_type}\' no válido. '
                'Debe ser Automatic o Manual.'
            ),
        )

    display = _MANAGED_SERVICES[service_name]
    return run_powershell(
        f"Set-Service -Name '{service_name}' -StartupType {startup_type}",
        requires_admin=True,
        description=f'Set {display} startup type to {startup_type}',
    )


def get_network_adapters():
    """List all network adapters with details as structured JSON."""
    return run_powershell_json(
        'Get-NetAdapter | Select-Object Name, InterfaceDescription, '
        'Status, LinkSpeed, MacAddress, DriverVersion',
        description='List network adapters',
    )


# ---------------------------------------------------------------------------
# Network adapter enable / disable — Phase 2 Wave 2.
# Only physical adapters (HardwareInterface=True or ConnectorPresent=True,
# and Virtual=False) are considered manageable.
# ---------------------------------------------------------------------------

# Allowed chars in a Windows adapter name when interpolated into PS single-quotes
_ADAPTER_NAME_RE = re.compile(r'^[a-zA-Z0-9 \-_.()]{1,64}$')


def _is_safe_adapter_name(name: str) -> bool:
    """Return True if name is safe to interpolate into a PS single-quoted string."""
    return bool(_ADAPTER_NAME_RE.match(name)) and "'" not in name


def get_manageable_adapters() -> dict:
    """
    Return all network adapters enriched with manageability metadata.

    Physical adapters (HardwareInterface=True or ConnectorPresent=True,
    and Virtual=False) are manageable; virtual/software adapters are listed
    but marked non-manageable so the UI can show them read-only.
    """
    result = run_powershell_json(
        'Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, '
        'MediaType, MacAddress, Virtual, HardwareInterface, ConnectorPresent',
        description='List network adapters with manageability info',
    )

    raw = result.details.get('data') if result.details else None
    if isinstance(raw, dict):
        raw = [raw]

    if result.is_error or not isinstance(raw, list):
        return {
            'status': 'error',
            'message': result.error or 'Error al consultar adaptadores de red',
            'adapters': [],
        }

    _MEDIA_LABELS = {
        '802.3': 'Ethernet',
        'Native 802.11': 'Wi-Fi',
        'Tunnel': 'Túnel / VPN',
        'Wireless WAN': 'WWAN',
        'Bluetooth': 'Bluetooth',
    }

    adapters = []
    for item in raw:
        name = item.get('Name', '') or ''
        virtual = bool(item.get('Virtual', False))
        hw_iface = bool(item.get('HardwareInterface', False))
        connector = bool(item.get('ConnectorPresent', False))
        manageable = (hw_iface or connector) and not virtual

        media_raw = item.get('MediaType', '') or ''
        media_label = _MEDIA_LABELS.get(media_raw, media_raw or 'Desconocido')

        adapters.append({
            'name': name,
            'description': item.get('InterfaceDescription', '') or '',
            'status': item.get('Status', '') or '',
            'media_type': media_label,
            'mac_address': item.get('MacAddress', '') or '',
            'virtual': virtual,
            'manageable': manageable,
        })

    return {'status': 'success', 'adapters': adapters}


def enable_adapter(adapter_name: str) -> CommandResult:
    """Enable a network adapter by name. Requires admin."""
    if not _is_safe_adapter_name(adapter_name):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f"Nombre de adaptador no válido: {adapter_name!r}",
        )
    return run_powershell(
        f"Enable-NetAdapter -Name '{adapter_name}' -Confirm:$false",
        requires_admin=True,
        description=f'Enable network adapter: {adapter_name}',
    )


def disable_adapter(adapter_name: str) -> CommandResult:
    """Disable a network adapter by name. Requires admin."""
    if not _is_safe_adapter_name(adapter_name):
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f"Nombre de adaptador no válido: {adapter_name!r}",
        )
    return run_powershell(
        f"Disable-NetAdapter -Name '{adapter_name}' -Confirm:$false",
        requires_admin=True,
        description=f'Disable network adapter: {adapter_name}',
    )


def get_ip_configuration():
    """Get full IP configuration."""
    return run_cmd('ipconfig /all', description='Full IP configuration')


def show_smb_sessions():
    """Show active SMB/network sessions."""
    return run_cmd('net use', description='Show network sessions')


def clear_smb_sessions():
    """Clear all mapped network drives and SMB sessions."""
    results = []
    r1 = run_cmd('net use * /delete /y', description='Delete mapped drives')
    results.append(r1.to_dict())
    r2 = run_cmd('nbtstat -R', description='Purge NetBIOS cache')
    results.append(r2.to_dict())
    return CommandResult(
        status=CommandStatus.SUCCESS,
        output='SMB sessions and NetBIOS cache cleared.',
        details={'steps': results},
    )


def show_proxy_settings():
    """Show WinHTTP proxy configuration."""
    return run_cmd('netsh winhttp show proxy', description='Show WinHTTP proxy')


def show_network_services():
    """Check status of network-related Windows services as structured JSON."""
    return run_powershell_json(
        "Get-Service wuauserv,BITS,cryptsvc,Dnscache,Dhcp,"
        "LanmanWorkstation,LanmanServer -ErrorAction SilentlyContinue | "
        "Select-Object Name, DisplayName, Status, StartType",
        description='Check network-related services',
    )


def get_shared_folders():
    """List shared folders on this computer."""
    return run_cmd('net share', description='List shared folders')


def purge_netbios_cache():
    """Purge NetBIOS name cache."""
    return run_cmd('nbtstat -R', description='Purge NetBIOS cache')


def run_network_repair():
    """
    Run a standard network repair sequence:
    1. Flush DNS
    2. Release IP
    3. Renew IP
    4. Set autotuning to normal
    """
    results = {}
    steps = [
        ('flush_dns', flush_dns),
        ('release_ip', release_ip),
        ('renew_ip', renew_ip),
        ('autotuning', set_autotuning_normal),
    ]
    for key, func in steps:
        results[key] = func().to_dict()
    return results
