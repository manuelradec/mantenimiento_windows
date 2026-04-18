"""
Policy Engine - Server-side enforcement of action execution rules.

Validates every action request against:
- Current operation mode
- Admin privilege requirements
- Risk class restrictions
- Mutual exclusion / locking
- Confirmation requirements
"""
import logging
import threading
import time
from typing import Optional

from core.action_registry import (
    ActionDef, RiskClass, OperationMode, MODE_ALLOWED_RISKS
)

logger = logging.getLogger('cleancpu.policy')


class PolicyViolation(Exception):
    """Raised when an action violates the current policy."""
    def __init__(self, message: str, violation_type: str = 'policy_violation'):
        super().__init__(message)
        self.violation_type = violation_type


class PolicyEngine:
    """
    Enforces execution policy for all maintenance actions.

    Thread-safe: uses a lock for mode changes and action locks.
    """

    def __init__(self):
        self._mode = OperationMode.SAFE_MAINTENANCE  # Default: safe maintenance
        self._lock = threading.Lock()
        # module -> {'job_id': str, 'acquired_at': float (unix ts)}
        self._active_locks: dict[str, dict] = {}
        self._confirmed_tokens: set[str] = set()  # Set of confirmed action tokens

    @property
    def mode(self) -> OperationMode:
        return self._mode

    def set_mode(self, mode: OperationMode):
        """Change the operation mode."""
        with self._lock:
            old_mode = self._mode
            self._mode = mode
            logger.info(f"Operation mode changed: {old_mode.value} -> {mode.value}")

    def validate_action(self, action: ActionDef, is_admin: bool,
                        confirmation_token: Optional[str] = None) -> dict:
        """
        Validate whether an action is allowed under current policy.

        Returns a dict with:
            allowed: bool
            reason: str (if not allowed)
            warnings: list[str]
            needs_confirmation: bool
            needs_restore_point: bool
            needs_reboot: bool
        """
        warnings = []
        allowed_risks = MODE_ALLOWED_RISKS[self._mode]

        # 1. Check risk class against mode
        if action.risk_class not in allowed_risks:
            return {
                'allowed': False,
                'reason': (
                    f'Action "{action.name}" has risk level "{action.risk_class.value}" '
                    f'which is not allowed in "{self._mode.value}" mode. '
                    f'Switch to a higher mode to use this action.'
                ),
                'violation_type': 'mode_restriction',
            }

        # 2. Check admin privileges
        if action.requires_admin and not is_admin:
            return {
                'allowed': False,
                'reason': f'Action "{action.name}" requires administrator privileges.',
                'violation_type': 'requires_admin',
            }

        # 3. Check mutual exclusion
        with self._lock:
            if action.module in self._active_locks:
                active_job = self._active_locks[action.module].get('job_id', '?')
                return {
                    'allowed': False,
                    'reason': (
                        f'Module "{action.module}" is currently locked by job {active_job}. '
                        f'Wait for it to complete before running another action.'
                    ),
                    'violation_type': 'locked',
                }

        # 4. Check confirmation requirement
        needs_confirmation = action.requires_confirmation
        if needs_confirmation and confirmation_token:
            if confirmation_token in self._confirmed_tokens:
                needs_confirmation = False
                self._confirmed_tokens.discard(confirmation_token)

        # 5. Build warnings
        if action.needs_reboot:
            warnings.append('This action may require a system reboot.')
        if action.needs_restore_point:
            warnings.append('Creating a restore point before this action is recommended.')
        if action.risk_class == RiskClass.DESTRUCTIVE:
            warnings.append('This is a DESTRUCTIVE action. Use with extreme caution.')

        return {
            'allowed': True,
            'warnings': warnings,
            'needs_confirmation': needs_confirmation,
            'confirm_message': action.confirm_message if needs_confirmation else '',
            'needs_restore_point': action.needs_restore_point,
            'needs_reboot': action.needs_reboot,
            'risk_class': action.risk_class.value,
        }

    def add_confirmation(self, token: str):
        """Register a confirmed action token."""
        self._confirmed_tokens.add(token)

    def acquire_lock(self, module: str, job_id: str) -> bool:
        """Acquire an execution lock for a module."""
        with self._lock:
            if module in self._active_locks:
                return False
            self._active_locks[module] = {
                'job_id': job_id,
                'acquired_at': time.time(),
            }
            logger.debug(f"Lock acquired: module={module!r} job={job_id}")
            return True

    def release_lock(self, module: str) -> bool:
        """Release an execution lock for a module. Returns True if a lock was released."""
        with self._lock:
            entry = self._active_locks.pop(module, None)
            if entry is not None:
                logger.debug(
                    f"Lock released: module={module!r} job={entry.get('job_id')}"
                )
                return True
            return False

    def force_release_lock(self, module: str) -> Optional[dict]:
        """
        Administratively release a stuck lock.

        Returns the previous lock entry (job_id + acquired_at) or None if no
        lock was held. Callers should log the forced release for audit.
        """
        with self._lock:
            entry = self._active_locks.pop(module, None)
            if entry is not None:
                logger.warning(
                    f"Lock force-released: module={module!r} "
                    f"job={entry.get('job_id')} "
                    f"held_for={time.time() - entry.get('acquired_at', time.time()):.1f}s"
                )
            return entry

    def get_active_locks(self) -> dict[str, dict]:
        """Return a detailed snapshot of active locks with age in seconds."""
        now = time.time()
        with self._lock:
            return {
                module: {
                    'job_id': info.get('job_id', ''),
                    'acquired_at': info.get('acquired_at', now),
                    'age_seconds': round(now - info.get('acquired_at', now), 1),
                }
                for module, info in self._active_locks.items()
            }

    def get_status(self) -> dict:
        """
        Get current policy engine status.

        The ``active_locks`` field preserves its legacy contract
        ({module: job_id_str}) so existing clients keep working. Detailed
        lock metadata (timestamp / age) is exposed separately under
        ``active_locks_detailed`` — new consumers should prefer that key,
        or call ``get_active_locks()`` directly.
        """
        with self._lock:
            # Legacy shape preserved for backward compatibility.
            legacy_locks = {
                module: info.get('job_id', '')
                for module, info in self._active_locks.items()
            }
        return {
            'mode': self._mode.value,
            'active_locks': legacy_locks,
            'active_locks_detailed': self.get_active_locks(),
            'allowed_risk_classes': [r.value for r in MODE_ALLOWED_RISKS[self._mode]],
        }


# Global policy engine instance
policy = PolicyEngine()
