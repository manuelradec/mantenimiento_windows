"""
Governance Layer - Mandatory enforcement bridge between routes and services.

Every mutating action MUST go through execute_governed_action().
This ensures:
- Action is registered in action_registry
- Policy engine validates risk class, mode, admin, confirmation
- Before/after snapshots are captured
- Execution flows through job_runner (with locking, audit)
- Results are persisted to SQLite
- Rollback info is recorded
- JSONL event log is written

NO mutating route may call service functions directly.
"""
import json
import os
import logging
from datetime import datetime
from typing import Callable, Optional

from flask import current_app

from core.action_registry import registry, RiskClass
from core.job_runner import job_runner
from core.persistence import get_db
from services.permissions import is_admin

logger = logging.getLogger('cleancpu.governance')


# ============================================================
# JSONL Event Logger
# ============================================================

def _get_jsonl_path() -> str:
    from config import Config
    return os.path.join(Config.LOG_DIR, 'events.jsonl')


def write_jsonl_event(event: dict):
    """Append a structured event to the JSONL log."""
    event['_ts'] = datetime.now().isoformat()
    try:
        path = _get_jsonl_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, default=str) + '\n')
    except Exception as e:
        logger.warning(f"JSONL write failed: {e}")


# ============================================================
# Before/After Snapshot Collection
# ============================================================

def capture_snapshot(snapshot_type: str, action_id: str = '') -> dict:
    """
    Capture a lightweight system state snapshot.
    Returns a dict suitable for JSON storage.
    On non-Windows or errors, returns partial data.
    """
    import sys
    snapshot = {
        'type': snapshot_type,
        'captured_at': datetime.now().isoformat(),
        'action_id': action_id,
    }
    try:
        import psutil
        # Disk usage
        disk = psutil.disk_usage('C:\\' if sys.platform == 'win32' else '/')
        snapshot['disk_total_gb'] = round(disk.total / (1024**3), 2)
        snapshot['disk_used_gb'] = round(disk.used / (1024**3), 2)
        snapshot['disk_free_gb'] = round(disk.free / (1024**3), 2)
        snapshot['disk_percent'] = disk.percent

        # Memory
        mem = psutil.virtual_memory()
        snapshot['ram_used_gb'] = round(mem.used / (1024**3), 2)
        snapshot['ram_percent'] = mem.percent

        # CPU
        snapshot['cpu_percent'] = psutil.cpu_percent(interval=0.5)

        # Process count
        snapshot['process_count'] = len(list(psutil.process_iter()))
    except ImportError:
        snapshot['note'] = 'psutil not available'
    except Exception as e:
        snapshot['error'] = str(e)

    # Temp dir sizes (quick estimate)
    for label, env_var in [('user_temp', 'TEMP'), ('system_temp', 'SystemRoot')]:
        try:
            if label == 'user_temp':
                path = os.environ.get(env_var, '')
            else:
                path = os.path.join(os.environ.get(env_var, ''), 'Temp')
            if path and os.path.exists(path):
                total = sum(
                    f.stat().st_size for f in os.scandir(path)
                    if f.is_file(follow_symlinks=False)
                )
                snapshot[f'{label}_mb'] = round(total / (1024 * 1024), 2)
        except Exception:
            pass

    return snapshot


# ============================================================
# Rollback Strategy
# ============================================================

ROLLBACK_STRATEGIES = {
    # cleanup
    'cleanup.user_temp': {'reversible': 'no', 'instructions': 'Temp files are rebuilt by Windows automatically.'},
    'cleanup.windows_temp': {'reversible': 'no', 'instructions': 'System temp rebuilt automatically.'},
    'cleanup.recycle_bin': {'reversible': 'no', 'instructions': 'Recycle Bin contents are permanently deleted.'},
    'cleanup.dns_cache': {'reversible': 'auto', 'instructions': 'DNS cache rebuilds automatically on next lookup.'},
    'cleanup.inet_cache': {'reversible': 'no', 'instructions': 'Browser caches rebuild on next visit.'},
    'cleanup.software_dist': {'reversible': 'no', 'instructions': 'WU re-downloads as needed.'},
    'cleanup.prefetch': {'reversible': 'auto', 'instructions': 'Prefetch rebuilds automatically.'},
    'cleanup.store_cache': {'reversible': 'auto', 'instructions': 'Store cache rebuilds on next launch.'},
    'cleanup.scan_duplicates': {'reversible': 'n/a', 'instructions': 'Read-only scan, nothing changed.'},
    'cleanup.restart_explorer': {'reversible': 'auto', 'instructions': 'Explorer restarts automatically.'},
    'cleanup.cleanmgr': {'reversible': 'no', 'instructions': 'Cleaned files are permanently removed.'},
    'cleanup.retrim': {'reversible': 'n/a', 'instructions': 'TRIM is a normal SSD maintenance operation.'},
    'cleanup.defrag': {'reversible': 'n/a', 'instructions': 'Defrag is a normal HDD maintenance operation.'},
    'cleanup.component_cleanup': {'reversible': 'no', 'instructions': 'Superseded components are permanently removed. Use restore point to revert.'},
    # network
    'network.flush_dns': {'reversible': 'auto', 'instructions': 'DNS cache rebuilds automatically.'},
    'network.renew_ip': {'reversible': 'auto', 'instructions': 'IP is automatically assigned by DHCP.'},
    'network.set_autotuning': {'reversible': 'manual', 'instructions': 'Run: netsh int tcp set global autotuninglevel=<previous_value>'},
    'network.test_connectivity': {'reversible': 'n/a', 'instructions': 'Read-only test.'},
    'network.release_ip': {'reversible': 'manual', 'instructions': 'Run ipconfig /renew to get a new IP.'},
    'network.clear_smb': {'reversible': 'manual', 'instructions': 'Re-map network drives manually.'},
    'network.repair': {'reversible': 'partial', 'instructions': 'Network stack self-recovers. Re-map drives if needed.'},
    'network.reset_ip_stack': {'reversible': 'no', 'instructions': 'REBOOT REQUIRED. TCP/IP stack is rebuilt on reboot.'},
    'network.reset_winsock': {'reversible': 'no', 'instructions': 'REBOOT REQUIRED. Winsock catalog is rebuilt on reboot.'},
    # repair
    'repair.sfc': {'reversible': 'n/a', 'instructions': 'SFC repairs system files from cache. Use restore point to revert.'},
    'repair.dism_check': {'reversible': 'n/a', 'instructions': 'Read-only check.'},
    'repair.dism_scan': {'reversible': 'n/a', 'instructions': 'Read-only deep scan.'},
    'repair.dism_restore': {'reversible': 'partial', 'instructions': 'Repairs component store. Use restore point to revert.'},
    'repair.chkdsk_scan': {'reversible': 'n/a', 'instructions': 'Online read-only scan.'},
    'repair.chkdsk_schedule': {'reversible': 'manual', 'instructions': 'Cancel with: chkntfs /x C:'},
    'repair.winsat': {'reversible': 'n/a', 'instructions': 'Benchmark only.'},
    'repair.memory_diagnostic': {'reversible': 'manual', 'instructions': 'Cancel by not rebooting, or use bcdedit.'},
    'repair.full_sequence': {'reversible': 'partial', 'instructions': 'Individual steps vary. Use restore point to revert repairs.'},
    # update
    'update.scan': {'reversible': 'n/a', 'instructions': 'Scan only, no changes.'},
    'update.download': {'reversible': 'partial', 'instructions': 'Downloaded files can be cleaned from SoftwareDistribution.'},
    'update.install': {'reversible': 'manual', 'instructions': 'Uninstall updates via Settings > Update History > Uninstall updates.'},
    'update.open_settings': {'reversible': 'n/a', 'instructions': 'Opens settings page only.'},
    'update.hard_reset': {'reversible': 'manual', 'instructions': 'Renamed folders have timestamped backups. Rename back to restore.'},
    'update.resync_time': {'reversible': 'auto', 'instructions': 'Time re-syncs automatically.'},
    # security
    'security.update_signatures': {'reversible': 'no', 'instructions': 'Signature updates are cumulative and cannot be reverted.'},
    'security.set_cpu_load': {'reversible': 'manual', 'instructions': 'Set-MpPreference -ScanAvgCPULoadFactor <previous_value>'},
    'security.quick_scan': {'reversible': 'n/a', 'instructions': 'Scan only.'},
    'security.full_scan': {'reversible': 'n/a', 'instructions': 'Scan only.'},
    # power
    'power.set_balanced': {'reversible': 'manual', 'instructions': 'Switch back to desired plan via powercfg.'},
    'power.set_high_performance': {'reversible': 'manual', 'instructions': 'Switch back to Balanced via powercfg.'},
    'power.battery_report': {'reversible': 'n/a', 'instructions': 'Report generation only.'},
    'power.enable_hibernation': {'reversible': 'manual', 'instructions': 'Run: powercfg -h off'},
    'power.disable_hibernation': {'reversible': 'manual', 'instructions': 'Run: powercfg -h on'},
    # advanced
    'advanced.create_restore_point': {'reversible': 'n/a', 'instructions': 'Creates a safety checkpoint.'},
}


def get_rollback_info(action_id: str) -> dict:
    """Get rollback strategy for an action."""
    default = {'reversible': 'unknown', 'instructions': 'No rollback information available.'}
    return ROLLBACK_STRATEGIES.get(action_id, default)


# ============================================================
# Applicability Matrix
# ============================================================

def check_applicability(action_id: str) -> dict:
    """
    Check if an action is applicable on this system.
    Returns {'applicable': bool, 'reason': str}
    """
    import sys

    if sys.platform != 'win32':
        # On non-Windows, only allow read-only diagnostics that use psutil
        action = registry.get(action_id)
        if action and action.risk_class == RiskClass.SAFE_READONLY:
            return {'applicable': True, 'reason': 'Diagnostic (simulated on non-Windows)'}
        return {'applicable': False, 'reason': 'Windows-only action on non-Windows platform'}

    # SSD-specific checks
    if action_id in ('cleanup.retrim',):
        # Check SSD presence - will be validated at runtime
        return {'applicable': True, 'reason': 'SSD presence checked at runtime'}

    if action_id in ('cleanup.defrag',):
        return {'applicable': True, 'reason': 'HDD presence checked at runtime'}

    # Battery report only on laptops
    if action_id == 'power.battery_report':
        return {'applicable': True, 'reason': 'Battery presence checked at runtime'}

    return {'applicable': True, 'reason': 'Applicable'}


# ============================================================
# Core Governance Function
# ============================================================

def execute_governed_action(
    action_id: str,
    handler: Callable,
    params: Optional[dict] = None,
    confirmation_token: Optional[str] = None,
) -> dict:
    """
    THE single mandatory entry point for all mutating actions.

    Flow:
    1. Look up action in registry
    2. Check applicability
    3. Capture before-snapshot
    4. Submit to job_runner (which enforces policy, locking, audit)
    5. Capture after-snapshot
    6. Record rollback info
    7. Write JSONL event
    8. Return structured result

    Returns dict with status, job_id (if async), result data, snapshots, rollback info.
    """
    # 1. Registry lookup
    action = registry.get(action_id)
    if not action:
        logger.error(f"Action not registered: {action_id}")
        return {
            'status': 'error',
            'error': f'Action {action_id} is not registered in the action registry.',
        }

    # 2. Applicability check
    applicability = check_applicability(action_id)
    if not applicability['applicable']:
        write_jsonl_event({
            'event': 'action_not_applicable',
            'action_id': action_id,
            'reason': applicability['reason'],
        })
        return {
            'status': 'not_applicable',
            'error': applicability['reason'],
            'action_id': action_id,
        }

    # 3. Get context from Flask app
    try:
        session_id = current_app.config.get('SESSION_ID', 'unknown')
        hostname = current_app.config.get('HOSTNAME', 'unknown')
        username = current_app.config.get('USERNAME', 'unknown')
    except RuntimeError:
        session_id = 'unknown'
        hostname = 'unknown'
        username = 'unknown'

    admin = is_admin()

    # 4. Capture before-snapshot for mutating actions
    before_snapshot = None
    if action.risk_class != RiskClass.SAFE_READONLY:
        try:
            before_snapshot = capture_snapshot('before', action_id)
        except Exception as e:
            logger.warning(f"Before snapshot failed for {action_id}: {e}")

    # 5. Submit to job_runner (enforces policy, locking, creates audit entry)
    result = job_runner.submit(
        action=action,
        handler=handler,
        session_id=session_id,
        hostname=hostname,
        username=username,
        is_admin=admin,
        params=params,
        confirmation_token=confirmation_token,
    )

    # 6. If action was rejected or needs confirmation, return early
    if result.get('status') in ('rejected', 'needs_confirmation'):
        write_jsonl_event({
            'event': 'action_policy_result',
            'action_id': action_id,
            'result_status': result['status'],
            'reason': result.get('reason', result.get('confirm_message', '')),
        })
        return result

    # 7. Capture after-snapshot for completed sync actions
    after_snapshot = None
    if result.get('status') not in ('submitted',) and action.risk_class != RiskClass.SAFE_READONLY:
        try:
            after_snapshot = capture_snapshot('after', action_id)
        except Exception as e:
            logger.warning(f"After snapshot failed for {action_id}: {e}")

    # 8. Add rollback info
    rollback = get_rollback_info(action_id)

    # 9. Persist snapshots to DB
    job_id = result.get('job_id', '')
    if before_snapshot or after_snapshot:
        _persist_snapshots(job_id, session_id, action_id, before_snapshot, after_snapshot)

    # 10. Write JSONL event
    write_jsonl_event({
        'event': 'action_executed',
        'action_id': action_id,
        'job_id': job_id,
        'status': result.get('status', 'unknown'),
        'risk_class': action.risk_class.value,
        'rollback': rollback.get('reversible', 'unknown'),
        'has_before_snapshot': before_snapshot is not None,
        'has_after_snapshot': after_snapshot is not None,
    })

    # 11. Enrich result
    result['action_id'] = action_id
    result['risk_class'] = action.risk_class.value
    result['rollback_info'] = rollback
    if before_snapshot:
        result['before_snapshot'] = before_snapshot
    if after_snapshot:
        result['after_snapshot'] = after_snapshot
    result['needs_reboot'] = action.needs_reboot

    return result


def _persist_snapshots(job_id: str, session_id: str, action_id: str,
                       before: Optional[dict], after: Optional[dict]):
    """Store snapshots in the snapshots table."""
    try:
        with get_db() as conn:
            if before:
                conn.execute(
                    "INSERT INTO snapshots (job_id, session_id, action_id, snapshot_type, "
                    "captured_at, data_json) VALUES (?, ?, ?, 'before', ?, ?)",
                    (job_id, session_id, action_id, before.get('captured_at', ''),
                     json.dumps(before))
                )
            if after:
                conn.execute(
                    "INSERT INTO snapshots (job_id, session_id, action_id, snapshot_type, "
                    "captured_at, data_json) VALUES (?, ?, ?, 'after', ?, ?)",
                    (job_id, session_id, action_id, after.get('captured_at', ''),
                     json.dumps(after))
                )
    except Exception as e:
        logger.warning(f"Snapshot persistence failed: {e}")
