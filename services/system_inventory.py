"""
System Inventory / Snapshot Collector.

Collects a structured, enterprise-grade hardware and software inventory
for use in maintenance reports and technician display.

Single entry point: collect_inventory()
Returns a flat dict — all fields are strings or simple lists.
Missing values are returned as '' (never None, never raises).

Data collected:
  - Basic: timestamp, hostname, username, full user name
  - Hardware: manufacturer, model, serial, UUID, domain/workgroup
  - System: OS name/version/build/arch, processor, RAM total+modules, disks
  - Network: Ethernet and WiFi MAC+IPv4 addresses
  - Office: product name, version, ClickToRun config, architecture
"""
import os
import sys
import logging
import platform
from datetime import datetime

from services.command_runner import run_powershell, CommandStatus

logger = logging.getLogger('cleancpu.inventory')

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ps(script: str, timeout: int = 20) -> str:
    """Run a PowerShell snippet; return stripped output or '' on any error."""
    if sys.platform != 'win32':
        return ''
    try:
        r = run_powershell(script, timeout=timeout, description='inventory')
        return (r.output or '').strip() if r.status != CommandStatus.ERROR else ''
    except Exception:
        return ''


def _safe(value, fallback: str = '') -> str:
    """Return str(value) or fallback if value is falsy."""
    return str(value).strip() if value else fallback


# ---------------------------------------------------------------------------
# Section collectors
# ---------------------------------------------------------------------------

def _collect_basic() -> dict:
    ts = datetime.now()
    hostname = platform.node() or os.environ.get('COMPUTERNAME', '')
    username = os.environ.get('USERNAME', os.environ.get('USER', ''))

    # Attempt to resolve full user display name via WMI
    full_name = _ps(
        "try { "
        "  $u = ([adsi]\"WinNT://$env:COMPUTERNAME/$env:USERNAME,user\"); "
        "  $u.FullName "
        "} catch { '' }",
        timeout=10,
    )

    return {
        'date': ts.strftime('%d/%m/%Y'),
        'time': ts.strftime('%H:%M:%S'),
        'timestamp': ts.isoformat(),
        'hostname': hostname,
        'username': username,
        'full_name': full_name or username,
    }


def _collect_hardware() -> dict:
    # One compact WMI call for all hardware fields
    raw = _ps(
        "$cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue; "
        "$bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue; "
        "$pc = Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue; "
        "if ($cs -and $bios) { "
        "  $domain = if ($cs.PartOfDomain) { $cs.Domain } else { $cs.Workgroup }; "
        "  $joinType = if ($cs.PartOfDomain) { 'Domain' } else { 'Workgroup' }; "
        "  \"$($cs.Manufacturer)|$($cs.Model)|$($bios.SerialNumber)"
        "|$($pc.UUID)|$domain|$joinType\" "
        "} else { '||||||' }",
        timeout=20,
    )
    parts = raw.split('|') if raw else []
    return {
        'manufacturer': _safe(parts[0] if len(parts) > 0 else ''),
        'model': _safe(parts[1] if len(parts) > 1 else ''),
        'serial': _safe(parts[2] if len(parts) > 2 else ''),
        'uuid': _safe(parts[3] if len(parts) > 3 else ''),
        'domain': _safe(parts[4] if len(parts) > 4 else ''),
        'join_type': _safe(parts[5] if len(parts) > 5 else ''),
    }


def _collect_system() -> dict:
    # OS details
    os_raw = _ps(
        "$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue; "
        "if ($os) { "
        "  \"$($os.Caption)|$($os.Version)|$($os.BuildNumber)"
        "|$($os.OSArchitecture)\" "
        "} else { '|||' }",
        timeout=15,
    )
    os_parts = os_raw.split('|') if os_raw else []

    # Processor
    proc = _ps(
        "(Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue "
        "| Select-Object -First 1).Name",
        timeout=10,
    )

    # RAM total from psutil if available, else WMI
    ram_total = ''
    try:
        import psutil
        total_bytes = psutil.virtual_memory().total
        ram_total = f"{round(total_bytes / (1024 ** 3), 1)} GB"
    except Exception:
        wmi_ram = _ps(
            "$m = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue; "
            "if ($m) { [math]::Round($m.TotalPhysicalMemory/1GB,1).ToString() + ' GB' }",
            timeout=10,
        )
        ram_total = wmi_ram

    # RAM modules (individual DIMMs)
    mods_raw = _ps(
        "Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue "
        "| ForEach-Object { "
        "  $gb = [math]::Round($_.Capacity/1GB,1); "
        "  $type = switch ($_.SMBIOSMemoryType) { "
        "    20{'DDR'} 21{'DDR2'} 24{'DDR3'} 26{'DDR4'} 34{'DDR5'} default{'RAM'} }; "
        "  \"$($_.DeviceLocator)|${gb}GB|$type|$($_.Speed)MHz\" "
        "} | Out-String",
        timeout=15,
    )
    modules = []
    for line in (mods_raw or '').splitlines():
        line = line.strip()
        if '|' in line:
            p = line.split('|')
            modules.append({
                'slot': _safe(p[0] if len(p) > 0 else ''),
                'capacity': _safe(p[1] if len(p) > 1 else ''),
                'type': _safe(p[2] if len(p) > 2 else ''),
                'speed': _safe(p[3] if len(p) > 3 else ''),
            })

    # Physical disks
    disks_raw = _ps(
        "Get-PhysicalDisk -ErrorAction SilentlyContinue "
        "| ForEach-Object { "
        "  $gb = [math]::Round($_.Size/1GB,0); "
        "  \"$($_.FriendlyName)|${gb}GB|$($_.MediaType)|$($_.BusType)\" "
        "} | Out-String",
        timeout=15,
    )
    disks = []
    for line in (disks_raw or '').splitlines():
        line = line.strip()
        if '|' in line:
            p = line.split('|')
            disks.append({
                'model': _safe(p[0] if len(p) > 0 else ''),
                'capacity': _safe(p[1] if len(p) > 1 else ''),
                'media_type': _safe(p[2] if len(p) > 2 else ''),
                'bus_type': _safe(p[3] if len(p) > 3 else ''),
            })

    return {
        'os_name': _safe(os_parts[0] if len(os_parts) > 0 else ''),
        'os_version': _safe(os_parts[1] if len(os_parts) > 1 else ''),
        'os_build': _safe(os_parts[2] if len(os_parts) > 2 else ''),
        'os_arch': _safe(os_parts[3] if len(os_parts) > 3 else ''),
        'processor': proc,
        'ram_total': ram_total,
        'ram_modules': modules,
        'disks': disks,
    }


def _collect_network() -> dict:
    # Get adapters with IP addresses — separate Ethernet vs WiFi
    net_raw = _ps(
        "Get-NetAdapter -ErrorAction SilentlyContinue "
        "| Where-Object { $_.Status -eq 'Up' } "
        "| ForEach-Object { "
        "  $mac = $_.MacAddress; "
        "  $name = $_.Name; "
        "  $desc = $_.InterfaceDescription; "
        "  $type = if ($_.PhysicalMediaType -match 'WiFi|802.11|Wireless') "
        "    { 'WiFi' } "
        "    elseif ($_.PhysicalMediaType -match 'Ethernet|802.3') "
        "    { 'Ethernet' } "
        "    else { "
        "      if ($name -match 'Wi[-]?Fi|WLAN|Wireless') { 'WiFi' } "
        "      else { 'Ethernet' } "
        "    }; "
        "  $ip = (Get-NetIPAddress -InterfaceIndex $_.ifIndex "
        "    -AddressFamily IPv4 -ErrorAction SilentlyContinue "
        "    | Select-Object -First 1 -ExpandProperty IPAddress); "
        "  \"$type|$mac|$ip|$name\" "
        "} | Out-String",
        timeout=20,
    )

    eth_mac = eth_ip = wifi_mac = wifi_ip = ''
    for line in (net_raw or '').splitlines():
        line = line.strip()
        if '|' not in line:
            continue
        p = line.split('|')
        if len(p) < 3:
            continue
        kind, mac, ip = p[0].strip(), p[1].strip(), p[2].strip()
        if kind == 'Ethernet' and not eth_mac:
            eth_mac, eth_ip = mac, ip
        elif kind == 'WiFi' and not wifi_mac:
            wifi_mac, wifi_ip = mac, ip

    return {
        'ethernet_mac': eth_mac,
        'ethernet_ip': eth_ip,
        'wifi_mac': wifi_mac,
        'wifi_ip': wifi_ip,
    }


def _collect_office() -> dict:
    """
    Detect Office installation from registry without running ospp.vbs.
    Checks ClickToRun configuration and Uninstall keys.
    Returns structured dict; all fields default to '' if absent.
    """
    # Try ClickToRun config (Office 365 / Microsoft 365 / retail perpetual C2R)
    c2r_raw = _ps(
        "$c2r = 'HKLM:\\SOFTWARE\\Microsoft\\Office\\ClickToRun\\Configuration'; "
        "if (Test-Path $c2r) { "
        "  $p = Get-ItemProperty $c2r -ErrorAction SilentlyContinue; "
        "  $pf = $p.Platform; "
        "  $ver = $p.VersionToReport; "
        "  $rel = $p.ProductReleaseIds; "
        "  $chan = $p.CDNBaseUrl; "
        "  \"C2R|$pf|$ver|$rel|$chan\" "
        "} else { 'NONE||||' }",
        timeout=10,
    )
    c2r_parts = (c2r_raw or '').split('|')
    is_c2r = c2r_parts[0].strip() == 'C2R' if c2r_parts else False

    if is_c2r:
        platform_str = _safe(c2r_parts[1] if len(c2r_parts) > 1 else '')
        version = _safe(c2r_parts[2] if len(c2r_parts) > 2 else '')
        release_ids = _safe(c2r_parts[3] if len(c2r_parts) > 3 else '')
        cdn_url = _safe(c2r_parts[4] if len(c2r_parts) > 4 else '')
        # Determine channel name from CDN URL
        channel = ''
        if 'Current' in cdn_url:
            channel = 'Current'
        elif 'MonthlyEnterprise' in cdn_url:
            channel = 'MonthlyEnterprise'
        elif 'SemiAnnual' in cdn_url:
            channel = 'SemiAnnual'
        elif cdn_url:
            channel = 'Custom'
        product_name = release_ids.split(',')[0].strip() if release_ids else 'Microsoft 365'
    else:
        version = platform_str = release_ids = channel = product_name = ''

    # If no C2R, check MSI/volume uninstall registry for any Office product
    if not product_name:
        msi_raw = _ps(
            "$paths = @("
            "  'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall',"
            "  'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall'"
            "); "
            "foreach ($p in $paths) { "
            "  Get-ChildItem $p -ErrorAction SilentlyContinue "
            "  | ForEach-Object { Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue } "
            "  | Where-Object { $_.DisplayName -match 'Microsoft Office|Microsoft 365' } "
            "  | Select-Object -First 1 "
            "  | ForEach-Object { \"$($_.DisplayName)|$($_.DisplayVersion)\" } "
            "} | Select-Object -First 1",
            timeout=15,
        )
        if msi_raw and '|' in msi_raw:
            msi_parts = msi_raw.split('|', 1)
            product_name = _safe(msi_parts[0])
            version = _safe(msi_parts[1])

    return {
        'product_name': product_name,
        'version': version,
        'platform': platform_str,
        'release_ids': release_ids,
        'channel': channel,
        'is_c2r': is_c2r,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def collect_inventory() -> dict:
    """
    Collect a full system inventory snapshot.

    Returns a single flat/nested dict.  Every section is collected
    independently — a failure in one section does not affect the others.
    Missing fields are always ''.

    Sections:
      basic, hardware, system, network, office
    """
    result = {
        'basic': {},
        'hardware': {},
        'system': {},
        'network': {},
        'office': {},
    }

    collectors = {
        'basic': _collect_basic,
        'hardware': _collect_hardware,
        'system': _collect_system,
        'network': _collect_network,
        'office': _collect_office,
    }

    for section, fn in collectors.items():
        try:
            result[section] = fn()
        except Exception as e:
            logger.warning(f"Inventory section '{section}' failed: {e}")
            result[section] = {}

    return result
