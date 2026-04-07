"""
Governance Layer - Mandatory enforcement bridge between routes and services.

Every mutating action MUST go through execute_governed_action().
This ensures:
- Action is registered in action_registry
- Policy engine validates risk class, mode, admin, confirmation
- Action-aware before/after snapshots are captured
- Execution flows through job_runner (with locking, audit)
- Results are persisted to SQLite
- Rollback classification and instructions are recorded
- Event Viewer data is collected for relevant workflows
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
from core.snapshots import capture_action_snapshot
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
# Rollback Strategy — Structured Classification
# ============================================================
# Classification:
#   not_reversible    — cannot undo, data is gone
#   auto_reversible   — system rebuilds state automatically
#   manually_reversible — operator can reverse with documented steps
#   partially_reversible — some sub-steps can be undone, others cannot
#   not_applicable    — action is read-only or diagnostic, nothing to reverse
#
# Additional fields:
#   needs_reboot      — reboot required to complete rollback
#   restore_point_recommended — create restore point before executing
#   rollback_command  — exact command to reverse (if applicable)

ROLLBACK_STRATEGIES = {
    # cleanup
    'cleanup.user_temp': {
        'classification': 'auto_reversible',
        'reversible': 'no',
        'instructions': 'Temp files are rebuilt by Windows automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.windows_temp': {
        'classification': 'auto_reversible',
        'reversible': 'no',
        'instructions': 'System temp rebuilt automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.recycle_bin': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'Recycle Bin contents are permanently deleted.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.dns_cache': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'DNS cache rebuilds automatically on next lookup.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.inet_cache': {
        'classification': 'auto_reversible',
        'reversible': 'no',
        'instructions': 'Browser caches rebuild on next visit.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.software_dist': {
        'classification': 'auto_reversible',
        'reversible': 'no',
        'instructions': 'WU re-downloads as needed.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.prefetch': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'Prefetch rebuilds automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.store_cache': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'Store cache rebuilds on next launch.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.scan_duplicates': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Read-only scan, nothing changed.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.restart_explorer': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'Explorer restarts automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.cleanmgr': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'Cleaned files are permanently removed.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.retrim': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'TRIM is a normal SSD maintenance operation.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.defrag': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Defrag is a normal HDD maintenance operation.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'cleanup.component_cleanup': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'Superseded components are permanently removed. Use restore point to revert.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    'repair.component_cleanup': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'Superseded components are permanently removed. Use restore point to revert.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    # network
    'network.purge_netbios': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'NetBIOS cache rebuilds automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.flush_dns': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'DNS cache rebuilds automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.renew_ip': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'IP is automatically assigned by DHCP.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.set_autotuning': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Run: netsh int tcp set global autotuninglevel=<previous_value>',
        'rollback_command': 'netsh int tcp set global autotuninglevel=normal',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.test_connectivity': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Read-only test.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.release_ip': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Run ipconfig /renew to get a new IP.',
        'rollback_command': 'ipconfig /renew',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.clear_smb': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Re-map network drives manually.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.repair': {
        'classification': 'partially_reversible',
        'reversible': 'partial',
        'instructions': 'Network stack self-recovers. Re-map drives if needed.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.reset_ip_stack': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'REBOOT REQUIRED. TCP/IP stack is rebuilt on reboot.',
        'needs_reboot': True,
        'restore_point_recommended': True,
    },
    'network.reset_winsock': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'REBOOT REQUIRED. Winsock catalog is rebuilt on reboot.',
        'needs_reboot': True,
        'restore_point_recommended': True,
    },
    # repair
    'repair.sfc': {
        'classification': 'partially_reversible',
        'reversible': 'n/a',
        'instructions': 'SFC repairs system files from cache. Use restore point to revert.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    'repair.dism_check': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Read-only check.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'repair.dism_scan': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Read-only deep scan.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'repair.dism_restore': {
        'classification': 'partially_reversible',
        'reversible': 'partial',
        'instructions': 'Repairs component store. Use restore point to revert.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    'repair.chkdsk_scan': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Online read-only scan.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'repair.chkdsk_schedule': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Cancel with: chkntfs /x C:',
        'rollback_command': 'chkntfs /x C:',
        'needs_reboot': True,
        'restore_point_recommended': False,
    },
    'repair.winsat': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Benchmark only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'repair.memory_diagnostic': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Cancel by not rebooting, or use bcdedit.',
        'needs_reboot': True,
        'restore_point_recommended': False,
    },
    'repair.full_sequence': {
        'classification': 'partially_reversible',
        'reversible': 'partial',
        'instructions': 'Individual steps vary. Use restore point to revert repairs.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    # update
    'update.scan': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Scan only, no changes.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'update.download': {
        'classification': 'partially_reversible',
        'reversible': 'partial',
        'instructions': 'Downloaded files can be cleaned from SoftwareDistribution.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'update.install': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Uninstall updates via Settings > Update History > Uninstall updates.',
        'needs_reboot': True,
        'restore_point_recommended': True,
    },
    'update.open_settings': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Opens settings page only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'update.hard_reset': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Renamed folders have timestamped backups. '
                        'Rename SoftwareDistribution.bak.TIMESTAMP back to SoftwareDistribution.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    'update.resync_time': {
        'classification': 'auto_reversible',
        'reversible': 'auto',
        'instructions': 'Time re-syncs automatically.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # security
    'security.update_signatures': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'Signature updates are cumulative and cannot be reverted.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'security.set_cpu_load': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Set-MpPreference -ScanAvgCPULoadFactor <previous_value>',
        'rollback_command': 'Set-MpPreference -ScanAvgCPULoadFactor 50',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'security.quick_scan': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Scan only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'security.full_scan': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Scan only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'security.open_sac_settings': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Opens Windows Security settings page only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'security.disable_sac': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': (
            'Desactivar el Control Inteligente de Aplicaciones es IRREVERSIBLE. '
            'Una vez desactivado, solo se puede reactivar realizando una instalación '
            'limpia de Windows 11. Se recomienda crear un punto de restauración antes, '
            'aunque este no restaurará el estado de SAC si se reinicia el equipo.'
        ),
        'needs_reboot': True,
        'restore_point_recommended': True,
    },
    # power
    'power.set_balanced': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Switch back to desired plan via powercfg.',
        'rollback_command': 'powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'power.set_high_performance': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Switch back to Balanced via powercfg.',
        'rollback_command': 'powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'power.battery_report': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Report generation only.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'power.enable_hibernation': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Run: powercfg -h off',
        'rollback_command': 'powercfg -h off',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'power.disable_hibernation': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Run: powercfg -h on',
        'rollback_command': 'powercfg -h on',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # advanced
    'advanced.create_restore_point': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Creates a safety checkpoint.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # office — GUI launchers (no persistent system change)
    'office.safe_mode': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Launches Outlook with /safe flag only. Close the window to undo.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'office.configure_mail': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Opens the mail profile manager GUI. No change is made unless the technician acts inside the tool.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'office.scanpst': {
        'classification': 'not_applicable',
        'reversible': 'n/a',
        'instructions': 'Launches SCANPST.EXE GUI only. No change is made unless the technician runs a repair inside the tool.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # office — repair (modifies Office installation files)
    'office.repair_quick': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'If the quick repair causes issues, run an online repair or reinstall Office.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    'office.repair_online': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'If the online repair causes issues, reinstall Office from scratch.',
        'needs_reboot': False,
        'restore_point_recommended': True,
    },
    # network — service startup type
    'network.service_startup': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Run the same action again and select the opposite startup type '
            '(Automatic → Manual or Manual → Automatic) to revert.'
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # network — adapter enable / disable
    'network.enable_adapter': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Disable the adapter again via the Adaptadores de Red UI or Device Manager.'
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'network.disable_adapter': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Re-enable the adapter via the Adaptadores de Red UI, Device Manager, '
            'or run: Enable-NetAdapter -Name "nombre" -Confirm:$false'
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # office — search index (cleared and auto-rebuilt by Windows Search)
    'office.rebuild_index': {
        'classification': 'not_reversible',
        'reversible': 'no',
        'instructions': 'The previous index is deleted. Windows Search rebuilds it automatically after restart (may take several minutes).',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # sharing — network discovery firewall group and NetBIOS per-adapter
    'sharing.enable_network_discovery': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Deshabilitar de nuevo via la UI de Uso Compartido, o ejecutar: '
            "Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752' | Disable-NetFirewallRule"
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'sharing.disable_network_discovery': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Habilitar de nuevo via la UI de Uso Compartido, o ejecutar: '
            "Get-NetFirewallRule -Group '@FirewallAPI.dll,-32752' | Enable-NetFirewallRule"
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'sharing.set_netbios': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Revertir via la UI de Uso Compartido seleccionando el modo anterior, '
            'o via Propiedades de Protocolo de Internet (TCP/IP) del adaptador.'
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    # startup — registry StartupApproved key or .lnk file rename
    'startup.disable_item': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': (
            'Re-enable via the Inicio Automático UI, or manually: '
            'for registry items restore the StartupApproved binary value to 0x02; '
            'for folder items rename the .lnk.disabled file back to .lnk.'
        ),
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
    'startup.enable_item': {
        'classification': 'manually_reversible',
        'reversible': 'manual',
        'instructions': 'Disable again via the Inicio Automático UI.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    },
}


def get_rollback_info(action_id: str) -> dict:
    """Get rollback strategy for an action with structured classification."""
    default = {
        'classification': 'unknown',
        'reversible': 'unknown',
        'instructions': 'No rollback information available.',
        'needs_reboot': False,
        'restore_point_recommended': False,
    }
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

    # 4. Capture action-aware before-snapshot for mutating actions
    before_snapshot = None
    if action.risk_class != RiskClass.SAFE_READONLY:
        try:
            before_snapshot = capture_action_snapshot(action_id, 'before')
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

    # 7. Capture action-aware after-snapshot for completed sync actions
    after_snapshot = None
    if result.get('status') not in ('submitted',) and action.risk_class != RiskClass.SAFE_READONLY:
        try:
            after_snapshot = capture_action_snapshot(action_id, 'after')
        except Exception as e:
            logger.warning(f"After snapshot failed for {action_id}: {e}")

    # 7b. Extract job_id early for use in event collection and persistence
    job_id = result.get('job_id', '')

    # 7c. Collect relevant Event Viewer data for applicable workflows
    event_viewer_data = None
    _evt_modules = {'repair', 'update', 'security', 'cleanup'}
    if action_id.split('.')[0] in _evt_modules and result.get('status') not in ('submitted',):
        try:
            event_viewer_data = _collect_events_for_action(
                action_id, session_id, job_id)
        except Exception as e:
            logger.warning(f"Event Viewer collection failed for {action_id}: {e}")

    # 8. Add rollback info
    rollback = get_rollback_info(action_id)

    # 9. Persist snapshots to DB
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
    if event_viewer_data:
        result['event_viewer_count'] = sum(
            len(v) for v in event_viewer_data.values() if isinstance(v, list)
        )
    result['needs_reboot'] = action.needs_reboot

    return result


def _collect_events_for_action(action_id: str, session_id: str,
                               job_id: str) -> Optional[dict]:
    """Collect relevant Event Viewer entries for a completed action."""
    import sys
    if sys.platform != 'win32':
        return None

    from services.event_viewer import (
        collect_update_events, collect_disk_errors,
        collect_defender_events, collect_application_errors,
        store_collected_events,
    )

    module = action_id.split('.')[0]

    # Dispatch table: module name → callable that returns the events dict for that module.
    # Each lambda is only called when the module matches, keeping imports lazy-safe.
    _MODULE_EVENT_COLLECTORS = {
        'update': lambda: {'update_events': collect_update_events(max_events=10)},
        'repair': lambda: {
            'application_errors': collect_application_errors(max_events=10),
            'disk_errors': collect_disk_errors(max_events=5),
        },
        'security': lambda: {'defender_events': collect_defender_events(max_events=10)},
        'cleanup': lambda: {'disk_errors': collect_disk_errors(max_events=5)},
    }

    collector_fn = _MODULE_EVENT_COLLECTORS.get(module)
    events = collector_fn() if collector_fn else {}

    if events:
        store_collected_events(session_id, events, job_id)

    return events if events else None


def _persist_snapshots(job_id: str, session_id: str, action_id: str,
                       before: Optional[dict], after: Optional[dict]):
    """Store snapshots in the snapshots table."""
    try:
        with get_db() as conn:
            if before:
                conn.execute(
                    "INSERT INTO snapshots (job_id, session_id, action_id, "
                    "snapshot_type, captured_at, data_json) "
                    "VALUES (?, ?, ?, 'before', ?, ?)",
                    (job_id, session_id, action_id,
                     before.get('captured_at', ''),
                     json.dumps(before, default=str))
                )
            if after:
                conn.execute(
                    "INSERT INTO snapshots (job_id, session_id, action_id, "
                    "snapshot_type, captured_at, data_json) "
                    "VALUES (?, ?, ?, 'after', ?, ?)",
                    (job_id, session_id, action_id,
                     after.get('captured_at', ''),
                     json.dumps(after, default=str))
                )
    except Exception as e:
        logger.warning(f"Snapshot persistence failed: {e}")
