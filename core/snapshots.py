"""
Action-Aware Snapshot Collectors.

Provides richer before/after state capture that is specific to the action
being executed, rather than just generic disk/RAM/CPU metrics.

Each collector returns a dict with a 'category' key and action-specific payload.
If a snapshot is not applicable, returns {applicable: False, reason: ...}.
"""
import os
import sys
import logging
from datetime import datetime

logger = logging.getLogger('cleancpu.snapshots')

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _safe_dir_size_mb(path: str) -> float:
    """Get directory size in MB, returning 0.0 on error."""
    total = 0
    try:
        if not os.path.exists(path):
            return -1.0  # does not exist
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    for sub in os.scandir(entry.path):
                        try:
                            if sub.is_file(follow_symlinks=False):
                                total += sub.stat(follow_symlinks=False).st_size
                        except (PermissionError, OSError):
                            pass
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        return 0.0
    return round(total / (1024 * 1024), 2)


def _disk_free_gb() -> float:
    """Get C: drive free space in GB."""
    if not HAS_PSUTIL:
        return -1.0
    try:
        disk = psutil.disk_usage('C:\\' if sys.platform == 'win32' else '/')
        return round(disk.free / (1024 ** 3), 2)
    except Exception:
        return -1.0


def _base_snapshot() -> dict:
    """Minimal base snapshot with timestamp and system metrics."""
    snap = {
        'captured_at': datetime.now().isoformat(),
    }
    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            snap['ram_used_gb'] = round(mem.used / (1024 ** 3), 2)
            snap['ram_percent'] = mem.percent
            snap['cpu_percent'] = psutil.cpu_percent(interval=0.3)
            snap['disk_free_gb'] = _disk_free_gb()
        except Exception as e:
            snap['error'] = str(e)
    return snap


# ============================================================
# Category-specific collectors
# ============================================================

def snapshot_cleanup(action_id: str) -> dict:
    """Snapshot for cleanup-related actions."""
    snap = _base_snapshot()
    snap['category'] = 'cleanup'

    user_temp = os.environ.get('TEMP', '')
    sys_root = os.environ.get('SystemRoot', 'C:\\Windows')
    win_temp = os.path.join(sys_root, 'Temp')
    prefetch = os.path.join(sys_root, 'Prefetch')
    sw_dist = os.path.join(sys_root, 'SoftwareDistribution', 'Download')

    snap['user_temp_mb'] = _safe_dir_size_mb(user_temp)
    snap['windows_temp_mb'] = _safe_dir_size_mb(win_temp)
    snap['prefetch_mb'] = _safe_dir_size_mb(prefetch)
    snap['sw_distribution_mb'] = _safe_dir_size_mb(sw_dist)

    # Recycle bin estimate via psutil if available
    snap['recycle_bin_estimate'] = 'not_collected'

    return snap


def snapshot_network(action_id: str) -> dict:
    """Snapshot for network-related actions."""
    snap = _base_snapshot()
    snap['category'] = 'network'

    if sys.platform != 'win32':
        snap['adapters'] = 'not_applicable'
        return snap

    # Collect adapter summary via PowerShell JSON
    try:
        from services.command_runner import run_powershell_json
        r = run_powershell_json(
            "Get-NetAdapter | Select-Object Name, Status, LinkSpeed, "
            "InterfaceDescription",
            timeout=30, description='Snapshot: network adapters'
        )
        if r.is_success and r.details.get('data'):
            data = r.details['data']
            if isinstance(data, dict):
                data = [data]
            snap['adapters'] = data
        else:
            snap['adapters'] = 'collection_failed'
    except Exception:
        snap['adapters'] = 'collection_error'

    # DNS config
    try:
        from services.command_runner import run_powershell_json
        r = run_powershell_json(
            "Get-DnsClientServerAddress -AddressFamily IPv4 | "
            "Select-Object InterfaceAlias, ServerAddresses",
            timeout=10, description='Snapshot: DNS config'
        )
        if r.is_success and r.details.get('data'):
            snap['dns_servers'] = r.details['data']
        else:
            snap['dns_servers'] = 'collection_failed'
    except Exception:
        snap['dns_servers'] = 'collection_error'

    return snap


def snapshot_power(action_id: str) -> dict:
    """Snapshot for power-related actions."""
    snap = _base_snapshot()
    snap['category'] = 'power'

    if sys.platform != 'win32':
        snap['active_plan'] = 'not_applicable'
        return snap

    try:
        from services.command_runner import run_cmd
        r = run_cmd('powercfg /GETACTIVESCHEME', description='Snapshot: active power plan')
        snap['active_plan'] = r.output.strip() if r.is_success else 'collection_failed'
    except Exception:
        snap['active_plan'] = 'collection_error'

    # Hibernation state
    try:
        hiberfil = 'C:\\hiberfil.sys'
        snap['hibernation_file_exists'] = os.path.exists(hiberfil)
    except Exception:
        snap['hibernation_file_exists'] = 'unknown'

    return snap


def snapshot_update(action_id: str) -> dict:
    """Snapshot for Windows Update / repair actions."""
    snap = _base_snapshot()
    snap['category'] = 'update'

    if sys.platform != 'win32':
        snap['wu_services'] = 'not_applicable'
        return snap

    # WU service states
    try:
        from services.command_runner import run_powershell_json
        r = run_powershell_json(
            "Get-Service wuauserv, BITS, cryptsvc, msiserver -ErrorAction "
            "SilentlyContinue | Select-Object Name, Status, StartType",
            timeout=10, description='Snapshot: WU services'
        )
        if r.is_success and r.details.get('data'):
            snap['wu_services'] = r.details['data']
        else:
            snap['wu_services'] = 'collection_failed'
    except Exception:
        snap['wu_services'] = 'collection_error'

    # SoftwareDistribution presence
    sys_root = os.environ.get('SystemRoot', 'C:\\Windows')
    sd_path = os.path.join(sys_root, 'SoftwareDistribution')
    snap['software_distribution_exists'] = os.path.exists(sd_path)
    snap['software_distribution_mb'] = _safe_dir_size_mb(
        os.path.join(sd_path, 'Download')
    )

    # catroot2 presence
    catroot2 = os.path.join(sys_root, 'System32', 'catroot2')
    snap['catroot2_exists'] = os.path.exists(catroot2)

    # Pending reboot signal
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
        )
        winreg.CloseKey(key)
        snap['reboot_pending'] = True
    except Exception:
        snap['reboot_pending'] = False

    return snap


def snapshot_security(action_id: str) -> dict:
    """Snapshot for Defender/security actions."""
    snap = _base_snapshot()
    snap['category'] = 'security'

    if sys.platform != 'win32':
        snap['defender'] = 'not_applicable'
        snap['smart_app_control'] = 'not_applicable'
        return snap

    try:
        from services.command_runner import run_powershell_json
        r = run_powershell_json(
            "Get-MpComputerStatus | Select-Object AMRunningMode, "
            "AntivirusEnabled, RealTimeProtectionEnabled, "
            "QuickScanAge, FullScanAge, AntivirusSignatureAge, "
            "NISEnabled",
            timeout=15, description='Snapshot: Defender status'
        )
        if r.is_success and r.details.get('data'):
            snap['defender'] = r.details['data']
        else:
            snap['defender'] = 'collection_failed'
    except Exception:
        snap['defender'] = 'collection_error'

    # Smart App Control state
    try:
        from services.smart_app_control import detect_smart_app_control_status
        sac_result = detect_smart_app_control_status()
        snap['smart_app_control'] = {
            'state': sac_result.details.get('state', 'unknown'),
            'supported': sac_result.details.get('supported', False),
            'detection_method': sac_result.details.get('detection_method', 'unknown'),
        }
    except Exception:
        snap['smart_app_control'] = 'collection_error'

    return snap


def snapshot_storage(action_id: str) -> dict:
    """Snapshot for SSD/HDD/storage actions."""
    snap = _base_snapshot()
    snap['category'] = 'storage'

    if sys.platform != 'win32':
        snap['disks'] = 'not_applicable'
        return snap

    try:
        from services.command_runner import run_powershell_json
        r = run_powershell_json(
            "Get-PhysicalDisk | Select-Object FriendlyName, MediaType, "
            "BusType, Size, HealthStatus, OperationalStatus",
            timeout=10, description='Snapshot: physical disks'
        )
        if r.is_success and r.details.get('data'):
            snap['disks'] = r.details['data']
        else:
            snap['disks'] = 'collection_failed'
    except Exception:
        snap['disks'] = 'collection_error'

    return snap


def snapshot_repair(action_id: str) -> dict:
    """Snapshot for OS repair actions (SFC, DISM, CHKDSK)."""
    snap = _base_snapshot()
    snap['category'] = 'repair'

    # Combine update-relevant data (WU services) with storage data
    if sys.platform == 'win32':
        # Pending reboot
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate'
                r'\Auto Update\RebootRequired'
            )
            winreg.CloseKey(key)
            snap['reboot_pending'] = True
        except Exception:
            snap['reboot_pending'] = False

        # Component store health indicator
        sys_root = os.environ.get('SystemRoot', 'C:\\Windows')
        winsxs = os.path.join(sys_root, 'WinSxS')
        snap['winsxs_exists'] = os.path.exists(winsxs)

    return snap


def snapshot_explorer(action_id: str) -> dict:
    """Snapshot for Explorer/shell actions."""
    snap = _base_snapshot()
    snap['category'] = 'explorer'

    if HAS_PSUTIL:
        explorer_procs = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'explorer.exe':
                    explorer_procs.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        snap['explorer_running'] = len(explorer_procs) > 0
        snap['explorer_pids'] = explorer_procs
    else:
        snap['explorer_running'] = 'unknown'

    return snap


# ============================================================
# Dispatcher — maps action_id prefix to the right collector
# ============================================================

_CATEGORY_MAP = {
    'cleanup': snapshot_cleanup,
    'network': snapshot_network,
    'power': snapshot_power,
    'update': snapshot_update,
    'security': snapshot_security,
    'repair': snapshot_repair,
    'advanced': snapshot_repair,  # restore points use repair-like snapshot
}

# Override for specific actions
_ACTION_OVERRIDES = {
    'cleanup.restart_explorer': snapshot_explorer,
    'cleanup.retrim': snapshot_storage,
    'cleanup.defrag': snapshot_storage,
}


def capture_action_snapshot(action_id: str, phase: str = 'before') -> dict:
    """
    Capture an action-aware snapshot.

    Dispatches to the correct collector based on action_id prefix.
    Falls back to base snapshot if no specific collector exists.

    Args:
        action_id: The action being executed (e.g. 'cleanup.user_temp')
        phase: 'before' or 'after'

    Returns:
        dict with category, phase, captured_at, and action-specific data
    """
    # Check overrides first
    collector = _ACTION_OVERRIDES.get(action_id)

    # Then check by module prefix
    if not collector:
        module = action_id.split('.')[0] if '.' in action_id else action_id
        collector = _CATEGORY_MAP.get(module)

    if collector:
        try:
            snap = collector(action_id)
        except Exception as e:
            logger.warning(f"Snapshot collector failed for {action_id}: {e}")
            snap = _base_snapshot()
            snap['category'] = 'fallback'
            snap['collector_error'] = str(e)
    else:
        snap = _base_snapshot()
        snap['category'] = 'generic'

    snap['phase'] = phase
    snap['action_id'] = action_id
    return snap
