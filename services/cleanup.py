"""
Cleanup and optimization module.

Handles: temp file cleanup, recycle bin, DNS cache, Explorer restart,
component cleanup, duplicate file scanning, SSD retrim, HDD defrag,
Store cache reset, prefetch cleanup.

Safety: No service-disabling operations. All cleanup targets are safe
directories that Windows rebuilds automatically.
"""
import os
import shutil
import hashlib
import logging
import sys
from collections import defaultdict

from services.command_runner import run_cmd, run_powershell, CommandStatus, CommandResult

logger = logging.getLogger('cleancpu.cleanup')


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
    if result.status == CommandStatus.ERROR and result.error and 'not find' in result.error.lower():
        return CommandResult(status=CommandStatus.SUCCESS,
                             output='Recycle Bin is already empty.')
    return result


def flush_dns_cache():
    """Clear the DNS resolver cache."""
    return run_cmd('ipconfig /flushdns', description='Flush DNS cache')


def run_cleanmgr():
    """Run Windows Disk Cleanup utility."""
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
    """
    Restart Windows Explorer (taskbar refresh).

    Reports accurate status: only SUCCESS if both stop and start succeed.
    """
    stop_result = run_cmd(
        'taskkill /f /im explorer.exe',
        description='Stop Explorer',
    )

    start_result = run_cmd(
        'start explorer.exe',
        shell=True,
        description='Start Explorer',
    )

    # Determine overall status based on sub-steps
    sub_results = {
        'stop': stop_result.to_dict(),
        'start': start_result.to_dict(),
    }

    if stop_result.is_error:
        return CommandResult(
            status=CommandStatus.ERROR,
            output='Failed to stop Explorer.',
            error=stop_result.error,
            details=sub_results,
        )

    if start_result.is_error:
        return CommandResult(
            status=CommandStatus.WARNING,
            output='Explorer stopped but may not have restarted properly.',
            error=start_result.error,
            details=sub_results,
        )

    return CommandResult(
        status=CommandStatus.SUCCESS,
        output='Explorer restarted successfully.',
        details=sub_results,
    )


def retrim_ssd():
    """Run TRIM optimization on SSD drives."""
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
    hdd_check = run_powershell(
        "(Get-PhysicalDisk | Where-Object MediaType -eq 'HDD').Count",
        description='Count HDDs',
    )

    if hdd_check.output.strip() == '0' or not hdd_check.output.strip():
        return CommandResult(
            status=CommandStatus.NOT_APPLICABLE,
            output='No HDD detected. Defragmentation skipped (SSD does not need defrag).',
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

    Uses a two-phase approach:
    1. Group files by size (quick filter)
    2. SHA-256 hash for size-matched files (accurate dedup)

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

    # Phase 1: Group by file size
    size_map = defaultdict(list)
    file_count = 0
    error_count = 0

    for root, dirs, files in os.walk(target):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                file_size = os.path.getsize(filepath)
                if file_size == 0:
                    continue
                size_map[file_size].append(filepath)
                file_count += 1
            except (PermissionError, OSError):
                error_count += 1

    # Phase 2: Hash only size-matched candidates using SHA-256
    hash_map = defaultdict(list)
    candidates = {size: paths for size, paths in size_map.items() if len(paths) > 1}

    for file_size, paths in candidates.items():
        for filepath in paths:
            try:
                hasher = hashlib.sha256()
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        hasher.update(chunk)
                file_hash = hasher.hexdigest()
                hash_map[file_hash].append({
                    'path': filepath,
                    'name': os.path.basename(filepath),
                    'size': file_size,
                })
            except (PermissionError, OSError):
                error_count += 1

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


def restart_sysmain():
    """
    Restart SysMain (Superfetch) service to clear its cache.
    Safe operation - does not permanently disable the service.
    """
    result = run_powershell(
        'Restart-Service SysMain -Force -ErrorAction SilentlyContinue',
        requires_admin=True,
        description='Restart SysMain service (clear cache)',
    )
    if result.status == CommandStatus.SUCCESS:
        result.output = 'SysMain service restarted. Cache cleared safely.'
    return result


def restart_windows_search():
    """
    Restart Windows Search service to clear its cache and rebuild index.
    Safe operation - does not permanently disable the service.
    """
    result = run_powershell(
        'Restart-Service WSearch -Force -ErrorAction SilentlyContinue',
        requires_admin=True,
        description='Restart Windows Search service (rebuild index)',
    )
    if result.status == CommandStatus.SUCCESS:
        result.output = 'Windows Search service restarted. Index will rebuild automatically.'
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
