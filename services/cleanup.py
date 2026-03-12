"""
Cleanup and optimization module.

Handles: temp file cleanup, recycle bin, DNS cache, Explorer restart,
component cleanup, duplicate file scanning, SSD retrim, HDD defrag,
optional SysMain/WSearch management.
"""
import os
import shutil
import hashlib
import logging
import sys
from collections import defaultdict

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('maintenance.cleanup')


def clean_user_temp():
    """Clean user temporary files."""
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    temp_path = os.environ.get('TEMP', '')
    if not temp_path or not os.path.exists(temp_path):
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='TEMP path not found.')

    return _clean_directory(temp_path, 'User TEMP')


def clean_windows_temp():
    """Clean Windows system temporary files."""
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    temp_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Temp')
    if not os.path.exists(temp_path):
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Windows Temp not found.')

    return _clean_directory(temp_path, 'Windows Temp')


def clean_software_distribution():
    """Clean Windows Update download cache."""
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'),
                        'SoftwareDistribution', 'Download')
    if not os.path.exists(path):
        return CommandResult(status=CommandStatus.NOT_APPLICABLE,
                             output='SoftwareDistribution\\Download not found.')

    return _clean_directory(path, 'SoftwareDistribution Download')


def clean_inet_cache():
    """Clean Internet cache files."""
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    paths = [
        os.path.join(os.environ.get('USERPROFILE', ''),
                     'AppData', 'Local', 'Microsoft', 'Windows', 'INetCache'),
        os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'),
                     'System32', 'config', 'systemprofile',
                     'AppData', 'Local', 'Microsoft', 'Windows', 'INetCache'),
    ]

    total_cleaned = 0
    total_errors = 0
    messages = []
    for path in paths:
        if os.path.exists(path):
            result = _clean_directory(path, f'INetCache ({path})')
            total_cleaned += result.details.get('files_deleted', 0)
            total_errors += result.details.get('errors', 0)
            messages.append(result.output)

    return CommandResult(
        status=CommandStatus.SUCCESS,
        output='\n'.join(messages) if messages else 'No INetCache directories found.',
        details={'files_deleted': total_cleaned, 'errors': total_errors},
    )


def empty_recycle_bin():
    """Empty the Windows Recycle Bin."""
    result = run_powershell(
        'Clear-RecycleBin -Confirm:$false -ErrorAction SilentlyContinue',
        description='Empty Recycle Bin',
    )
    if result.status == CommandStatus.ERROR and 'not find' in result.error.lower():
        return CommandResult(status=CommandStatus.SUCCESS,
                             output='Recycle Bin is already empty.')
    return result


def flush_dns_cache():
    """Clear the DNS resolver cache."""
    return run_cmd('ipconfig /flushdns', description='Flush DNS cache')


def run_cleanmgr():
    """Run Windows Disk Cleanup utility."""
    # First configure the cleanup options, then run
    result = run_cmd(
        'cleanmgr /sagerun:1',
        requires_admin=True,
        timeout=300,
        description='Run Disk Cleanup (cleanmgr)',
    )
    return result


def dism_component_cleanup():
    """Run DISM StartComponentCleanup to remove superseded components."""
    result = run_cmd(
        'DISM /Online /Cleanup-Image /StartComponentCleanup',
        requires_admin=True,
        timeout=600,
        description='DISM StartComponentCleanup',
    )
    return result


def restart_explorer():
    """Restart Windows Explorer (taskbar refresh)."""
    result = run_cmd(
        'taskkill /f /im explorer.exe',
        description='Stop Explorer',
    )
    start_result = run_cmd(
        'start explorer.exe',
        shell=True,
        description='Start Explorer',
    )
    return CommandResult(
        status=CommandStatus.SUCCESS,
        output='Explorer restarted successfully.',
        details={'stop': result.to_dict(), 'start': start_result.to_dict()},
    )


def retrim_ssd():
    """Run TRIM optimization on SSD drives."""
    # First check if SSD exists
    check = run_powershell(
        "Get-PhysicalDisk | Where-Object MediaType -eq 'SSD' | "
        "Select-Object FriendlyName",
        description='Check for SSD presence',
    )
    if check.status != CommandStatus.SUCCESS or not check.output.strip():
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='No SSD detected. ReTrim not applicable.',
        )

    result = run_powershell(
        'Optimize-Volume -DriveLetter C -ReTrim -Verbose',
        requires_admin=True,
        timeout=120,
        description='ReTrim SSD',
    )
    return result


def defrag_hdd():
    """Defragment HDD (only if HDD is detected, never SSD)."""
    # Check disk type first
    check = run_powershell(
        "Get-PhysicalDisk | Select-Object FriendlyName,MediaType | Format-Table -AutoSize",
        description='Check disk types for defrag',
    )

    # Verify HDD presence
    hdd_check = run_powershell(
        "(Get-PhysicalDisk | Where-Object MediaType -eq 'HDD').Count",
        description='Count HDDs',
    )

    if hdd_check.output.strip() == '0' or not hdd_check.output.strip():
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='No HDD detected. Defragmentation skipped (SSD does not need defrag).',
        )

    # Analyze first
    analysis = run_cmd(
        'defrag C: /A',
        requires_admin=True,
        timeout=120,
        description='Analyze disk fragmentation',
    )

    result = run_cmd(
        'defrag C: /O /U /V',
        requires_admin=True,
        timeout=600,
        description='Defragment HDD',
    )
    return result


def analyze_fragmentation():
    """Analyze disk fragmentation without performing defrag."""
    return run_cmd(
        'defrag C: /A',
        requires_admin=True,
        timeout=60,
        description='Analyze disk fragmentation',
    )


def scan_duplicate_files(directory=None):
    """
    Scan for duplicate files in the specified directory (default: Downloads).
    Returns duplicates grouped by hash. Does NOT delete anything.
    """
    if sys.platform != 'win32':
        target = directory or os.path.expanduser('~/Downloads')
    else:
        target = directory or os.path.join(
            os.environ.get('USERPROFILE', ''), 'Downloads'
        )

    if not os.path.exists(target):
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output=f'Directory not found: {target}',
        )

    hash_map = defaultdict(list)
    file_count = 0
    error_count = 0

    for root, dirs, files in os.walk(target):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                file_size = os.path.getsize(filepath)
                if file_size == 0:
                    continue
                # Quick hash: first 8KB + file size
                hasher = hashlib.md5()
                with open(filepath, 'rb') as f:
                    hasher.update(f.read(8192))
                hasher.update(str(file_size).encode())
                file_hash = hasher.hexdigest()
                hash_map[file_hash].append({
                    'path': filepath,
                    'name': filename,
                    'size': file_size,
                })
                file_count += 1
            except (PermissionError, OSError) as e:
                error_count += 1
                logger.debug(f"Cannot read {filepath}: {e}")

    duplicates = {h: files for h, files in hash_map.items() if len(files) > 1}
    dup_count = sum(len(files) - 1 for files in duplicates.values())

    return CommandResult(
        status=CommandStatus.SUCCESS,
        output=f'Scanned {file_count} files. Found {dup_count} duplicate(s) in {len(duplicates)} group(s).',
        details={
            'total_files': file_count,
            'duplicate_groups': len(duplicates),
            'duplicate_files': dup_count,
            'errors': error_count,
            'duplicates': {h: files for h, files in list(duplicates.items())[:50]},
            'directory': target,
        },
    )


def disable_sysmain():
    """
    Disable SysMain (Superfetch) service.
    WARNING: Only recommended on SSD-only systems. Can degrade HDD performance.
    """
    result = run_powershell(
        'Stop-Service SysMain -Force -ErrorAction SilentlyContinue; '
        'Set-Service SysMain -StartupType Disabled',
        requires_admin=True,
        description='Disable SysMain service',
    )
    return result


def disable_windows_search():
    """
    Disable Windows Search service.
    WARNING: This breaks Windows file search functionality.
    """
    result = run_powershell(
        'Stop-Service WSearch -Force -ErrorAction SilentlyContinue; '
        'Set-Service WSearch -StartupType Disabled',
        requires_admin=True,
        description='Disable Windows Search service',
    )
    return result


def reset_windows_store_cache():
    """Reset Windows Store cache."""
    return run_cmd(
        'wsreset.exe',
        timeout=60,
        description='Reset Windows Store cache',
    )


def clean_prefetch():
    """Clean Prefetch folder (optional, minimal benefit)."""
    if sys.platform != 'win32':
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Not on Windows.')

    prefetch_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Prefetch')
    if not os.path.exists(prefetch_path):
        return CommandResult(status=CommandStatus.NOT_APPLICABLE, output='Prefetch folder not found.')

    return _clean_directory(prefetch_path, 'Prefetch')


def _clean_directory(path, label):
    """
    Internal helper to clean files from a directory.
    Returns structured result with counts.
    """
    files_deleted = 0
    dirs_deleted = 0
    errors = 0
    freed_bytes = 0

    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    size = os.path.getsize(item_path)
                    os.unlink(item_path)
                    files_deleted += 1
                    freed_bytes += size
                elif os.path.isdir(item_path):
                    size = _get_dir_size(item_path)
                    shutil.rmtree(item_path, ignore_errors=True)
                    if not os.path.exists(item_path):
                        dirs_deleted += 1
                        freed_bytes += size
                    else:
                        errors += 1
            except PermissionError:
                errors += 1
            except OSError:
                errors += 1
    except PermissionError:
        return CommandResult(
            status=CommandStatus.ERROR,
            error=f'Permission denied accessing {path}',
            details={'path': path},
        )

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    status = CommandStatus.SUCCESS if errors == 0 else CommandStatus.WARNING

    return CommandResult(
        status=status,
        output=f'{label}: Deleted {files_deleted} files, {dirs_deleted} folders. '
               f'Freed {freed_mb} MB. {errors} error(s).',
        details={
            'path': path,
            'files_deleted': files_deleted,
            'dirs_deleted': dirs_deleted,
            'freed_mb': freed_mb,
            'errors': errors,
        },
    )


def _get_dir_size(path):
    """Get total size of a directory."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _get_dir_size(entry.path)
    except (PermissionError, OSError):
        pass
    return total
