"""
Network and connectivity module.

Handles: DNS flush, IP reset, network stack, TCP settings, connectivity tests,
SMB sessions, network adapters, proxy settings, service status.
"""
import logging

from services.command_runner import (
    run_cmd, run_powershell, run_powershell_json, CommandStatus, CommandResult
)

logger = logging.getLogger('maintenance.network')


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
    """Test network connectivity to a specific host and port."""
    import re
    # Sanitize host to prevent command injection
    if not re.match(r'^[a-zA-Z0-9.\-:]+$', str(host)):
        return CommandResult(
            status=CommandStatus.ERROR,
            error='Invalid host format. Only alphanumeric characters, dots, hyphens, and colons are allowed.',
        )
    port = int(port)
    if not (1 <= port <= 65535):
        return CommandResult(
            status=CommandStatus.ERROR,
            error='Invalid port. Must be between 1 and 65535.',
        )
    return run_powershell(
        f'Test-NetConnection -ComputerName {host} -Port {port}',
        timeout=30,
        description=f'Test connectivity to {host}:{port}',
    )


def get_network_adapters():
    """List all network adapters with details as structured JSON."""
    return run_powershell_json(
        'Get-NetAdapter | Select-Object Name, InterfaceDescription, '
        'Status, LinkSpeed, MacAddress, DriverVersion',
        description='List network adapters',
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
