"""
System diagnostics and information gathering.

All functions are read-only and safe to execute.
Covers: CPU, RAM, disk, OS version, architecture, uptime, temperature,
SMART status, TRIM, display events, top processes, services, drivers,
network overview, startup programs, remote access detection.
"""
import logging
import platform
import os
import sys
from datetime import datetime

logger = logging.getLogger('maintenance.system_info')

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from services.command_runner import (
    run_cmd, run_powershell, run_powershell_json, CommandStatus, CommandResult
)


def get_system_overview():
    """Get general system information."""
    info = {}

    if HAS_PSUTIL:
        info['cpu_count_logical'] = psutil.cpu_count(logical=True)
        info['cpu_count_physical'] = psutil.cpu_count(logical=False)
        info['cpu_percent'] = psutil.cpu_percent(interval=1)

        mem = psutil.virtual_memory()
        info['ram_total_gb'] = round(mem.total / (1024 ** 3), 2)
        info['ram_used_gb'] = round(mem.used / (1024 ** 3), 2)
        info['ram_percent'] = mem.percent

        disk = psutil.disk_usage('C:\\' if sys.platform == 'win32' else '/')
        info['disk_total_gb'] = round(disk.total / (1024 ** 3), 2)
        info['disk_used_gb'] = round(disk.used / (1024 ** 3), 2)
        info['disk_free_gb'] = round(disk.free / (1024 ** 3), 2)
        info['disk_percent'] = disk.percent

        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        info['boot_time'] = boot_time.strftime('%Y-%m-%d %H:%M:%S')
        info['uptime_hours'] = round(uptime.total_seconds() / 3600, 1)
        info['uptime_str'] = str(uptime).split('.')[0]

    info['os_name'] = platform.system()
    info['os_version'] = platform.version()
    info['os_release'] = platform.release()
    info['architecture'] = platform.machine()
    info['computer_name'] = platform.node()
    info['processor'] = platform.processor()
    info['python_version'] = platform.python_version()
    info['username'] = os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))

    return info


def get_windows_version():
    """Get detailed Windows version information as structured JSON."""
    result = run_powershell_json(
        '[System.Environment]::OSVersion | Select-Object Platform, '
        'ServicePack, Version, VersionString',
        description='Get Windows version details',
    )
    return result


def get_ram_details():
    """Get detailed RAM module information as structured JSON."""
    result = run_powershell_json(
        'Get-CimInstance Win32_PhysicalMemory | '
        'Select-Object BankLabel, '
        '@{N="CapacityGB";E={[math]::Round($_.Capacity/1GB,2)}}, '
        'Manufacturer, PartNumber, Speed, MemoryType',
        description='Get RAM module details',
    )
    return result


def get_disk_details():
    """Get physical disk information as structured JSON."""
    result = run_powershell_json(
        'Get-PhysicalDisk | Select-Object FriendlyName, MediaType, '
        'BusType, @{N="SizeGB";E={[math]::Round($_.Size/1GB,2)}}, '
        'HealthStatus',
        description='Get physical disk details',
    )
    return result


def get_smart_status():
    """Get disk health/SMART status as structured JSON."""
    result = run_powershell_json(
        'Get-PhysicalDisk | Select-Object FriendlyName, HealthStatus, '
        'OperationalStatus',
        description='Get disk SMART/health status',
    )
    return result


def get_trim_status():
    """Check TRIM status for SSDs."""
    result = run_cmd(
        'fsutil behavior query DisableDeleteNotify',
        requires_admin=True,
        description='Check TRIM status',
    )
    return result


def get_display_events():
    """Get display/DWM related events from Windows Event Log."""
    result = run_powershell(
        'Get-WinEvent -FilterHashtable @{LogName="System"; ProviderName="*dwm*","*display*","*gpu*","*video*"} '
        '-MaxEvents 30 -ErrorAction SilentlyContinue | '
        'Select-Object TimeCreated,Id,LevelDisplayName,Message | '
        'Format-Table -AutoSize -Wrap',
        requires_admin=True,
        timeout=30,
        description='Get display/DWM events',
    )
    return result


def get_top_processes(count=15):
    """Get top CPU and RAM consuming processes."""
    if HAS_PSUTIL:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                pinfo = proc.info
                processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        by_cpu = sorted(processes, key=lambda x: x.get('cpu_percent', 0), reverse=True)[:count]
        by_ram = sorted(processes, key=lambda x: x.get('memory_percent', 0), reverse=True)[:count]

        return CommandResult(
            status=CommandStatus.SUCCESS,
            output='Process data retrieved via psutil.',
            details={'by_cpu': by_cpu, 'by_ram': by_ram},
        )

    # Fallback to PowerShell
    result = run_powershell(
        f'Get-Process | Sort-Object CPU -Descending | Select-Object -First {count} '
        'Name,Id,CPU,@{{N="MemMB";E={{[math]::Round($_.WorkingSet64/1MB,1)}}}} | '
        'Format-Table -AutoSize',
        description='Get top processes',
    )
    return result


def get_important_services():
    """Check status of important Windows services as structured JSON."""
    services = [
        'wuauserv', 'BITS', 'cryptsvc', 'msiserver', 'Spooler',
        'W32Time', 'WinDefend', 'mpssvc', 'EventLog', 'Dhcp',
        'Dnscache', 'LanmanWorkstation', 'LanmanServer',
        'WSearch', 'SysMain', 'TrustedInstaller',
    ]
    svc_list = "','".join(services)
    result = run_powershell_json(
        f"Get-Service -Name '{svc_list}' -ErrorAction SilentlyContinue | "
        "Select-Object Name, DisplayName, Status, StartType",
        description='Check important services status',
    )
    return result


def get_driver_list():
    """Enumerate installed drivers."""
    result = run_cmd(
        'pnputil /enum-drivers',
        description='Enumerate installed drivers',
    )
    return result


def get_problem_devices():
    """Find devices with problems."""
    result = run_cmd(
        'pnputil /enum-devices /problem',
        description='Find problematic devices',
    )
    return result


def get_network_overview():
    """Get basic network adapter information as structured JSON."""
    result = run_powershell_json(
        'Get-NetAdapter | Select-Object Name, InterfaceDescription, '
        'Status, LinkSpeed, MacAddress',
        description='Get network adapters',
    )
    return result


def get_route_table():
    """Get the IP route table."""
    result = run_cmd('route print', description='Get route table')
    return result


def get_startup_programs():
    """Get startup programs using modern CIM as structured JSON."""
    result = run_powershell_json(
        'Get-CimInstance Win32_StartupCommand | '
        'Select-Object Name, Command, Location, User',
        description='Get startup programs',
    )
    return result


def detect_remote_access_processes():
    """Detect remote access software that may be running."""
    remote_tools = [
        'AnyDesk', 'anydesk',
        'TeamViewer', 'teamviewer',
        'tvnserver', 'tvnviewer',
        'TightVNC', 'winvnc',
        'UltraVNC', 'ultravnc',
        'RustDesk', 'rustdesk',
        'ScreenConnect', 'screenconnect',
        'LogMeIn', 'logmein',
        'msra',  # Windows Remote Assistance
        'mstsc',  # Remote Desktop Client
    ]
    if HAS_PSUTIL:
        found = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name'].lower()
                for tool in remote_tools:
                    if tool.lower() in name:
                        found.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'tool': tool,
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return CommandResult(
            status=CommandStatus.SUCCESS,
            output=f"Found {len(found)} remote access process(es).",
            details={'processes': found},
        )

    result = run_powershell(
        "Get-Process | Where-Object {$_.Name -match "
        "'anydesk|teamviewer|vnc|rustdesk|screenconnect|logmein|msra|mstsc'} | "
        "Select-Object Name,Id,CPU | Format-Table -AutoSize",
        description='Detect remote access processes',
    )
    return result


def get_temperature():
    """
    Attempt to read CPU/system temperature.
    NOTE: This is unreliable on many systems and may return empty results.
    """
    result = run_powershell(
        'Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature '
        '-ErrorAction SilentlyContinue | '
        'Select-Object InstanceName,@{N="TempCelsius";E={($_.CurrentTemperature - 2732) / 10}}',
        requires_admin=True,
        timeout=15,
        description='Read system temperature (may not be available)',
    )
    return result


def get_license_status():
    """Get Windows license/activation status."""
    result = run_cmd(
        'cscript //nologo C:\\Windows\\System32\\slmgr.vbs /dlv',
        timeout=30,
        description='Get Windows license status',
    )
    return result


def get_time_sync_status():
    """Get time synchronization status."""
    result = run_cmd(
        'w32tm /query /status',
        description='Get time sync status',
    )
    # Error code 0x80070426 means W32Time service is not running
    if result.return_code and (result.return_code == 2147943462 or
                               result.return_code == 0x80070426):
        result.status = CommandStatus.WARNING
        result.output = (
            'El servicio de Hora de Windows (W32Time) no está en ejecución.\n'
            'Use la función "Sincronizar hora" para iniciarlo.'
        )
        result.error = ''
    return result


def run_full_diagnostics():
    """Run all diagnostic checks and return combined results."""
    results = {}
    results['system_overview'] = get_system_overview()
    results['windows_version'] = get_windows_version().to_dict()
    results['ram_details'] = get_ram_details().to_dict()
    results['disk_details'] = get_disk_details().to_dict()
    results['smart_status'] = get_smart_status().to_dict()
    results['trim_status'] = get_trim_status().to_dict()
    results['top_processes'] = get_top_processes().to_dict()
    results['important_services'] = get_important_services().to_dict()
    results['problem_devices'] = get_problem_devices().to_dict()
    results['network_overview'] = get_network_overview().to_dict()
    results['startup_programs'] = get_startup_programs().to_dict()
    results['remote_access'] = detect_remote_access_processes().to_dict()
    return results
