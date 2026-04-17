"""
Job Runner - Background execution engine for long-running maintenance tasks.

Actions are submitted as jobs, executed in a thread pool, and tracked
with full lifecycle (queued -> running -> completed/failed/cancelled).

Frontend polls /api/jobs/<job_id> for status.
"""
import uuid
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Callable

from core.action_registry import ActionDef
from core.policy_engine import policy
from core.persistence import JobStore, AuditStore

logger = logging.getLogger('cleancpu.jobs')

# Maximum concurrent background jobs
MAX_WORKERS = 3

# CommandResult statuses that map to a job 'completed' outcome.
# All others are treated as 'failed'.
_COMPLETED_RESULT_STATUSES = frozenset({
    'success', 'warning', 'not_applicable', 'skipped',
})


def _apply_dict_result(job: 'Job', result: dict, duration_ms: int) -> None:
    """
    Apply a multi-step dict result to the job.
    Any sub-step with status 'error' or 'timeout' sets overall to 'partial_success'.
    """
    outputs = []
    has_error = False
    for key, val in result.items():
        if not isinstance(val, dict):
            continue
        step_status = val.get('status', 'unknown')
        if step_status in ('error', 'timeout'):
            has_error = True
        step_output = val.get('output', '')
        step_error = val.get('error', '')
        outputs.append(f"[{key}] {step_status}: {step_output or step_error}")

    job.output = '\n'.join(outputs)
    job.status = 'partial_success' if has_error else 'completed'
    job.duration_ms = duration_ms


def _apply_command_result(job: 'Job', result, duration_ms: int) -> None:
    """
    Apply a CommandResult (has .to_dict()) to the job.
    Maps CommandStatus values to job 'completed' or 'failed'.
    """
    rd = result.to_dict()
    job.output = rd.get('output', '')
    job.error = rd.get('error', '')
    job.return_code = rd.get('return_code')
    job.duration_ms = duration_ms
    status_val = rd.get('status', 'unknown')
    job.status = 'completed' if status_val in _COMPLETED_RESULT_STATUSES else 'failed'
    # For non-success completed statuses, echo the status as output when output is absent
    if job.status == 'completed' and status_val != 'success' and not job.output:
        job.output = status_val


def _apply_generic_result(job: 'Job', result, duration_ms: int) -> None:
    """Apply a plain (non-dict, non-CommandResult) return value to the job."""
    job.output = str(result) if result else ''
    job.status = 'completed'
    job.duration_ms = duration_ms


class Job:
    """Represents a single background job."""

    __slots__ = (
        'job_id', 'action_id', 'action_name', 'module', 'risk_class',
        'status', 'queued_at', 'started_at', 'completed_at',
        'output', 'error', 'return_code', 'duration_ms',
        'needs_reboot', 'progress', 'handler', 'params',
        'session_id', 'hostname', 'username', 'is_admin',
        'cancel_requested', 'process',
    )

    def __init__(self, action: ActionDef, session_id: str, hostname: str = '',
                 username: str = '', is_admin: bool = False,
                 handler: Optional[Callable] = None, params: Optional[dict] = None):
        self.job_id = str(uuid.uuid4())[:12]
        self.action_id = action.action_id
        self.action_name = action.name
        self.module = action.module
        self.risk_class = action.risk_class.value
        self.status = 'queued'
        self.queued_at = datetime.now().isoformat()
        self.started_at = None
        self.completed_at = None
        self.output = ''
        self.error = ''
        self.return_code = None
        self.duration_ms = 0
        self.needs_reboot = action.needs_reboot
        self.progress = 0
        self.handler = handler
        self.params = params or {}
        self.session_id = session_id
        self.hostname = hostname
        self.username = username
        self.is_admin = is_admin
        self.cancel_requested = False
        self.process = None

    def to_dict(self) -> dict:
        return {
            'job_id': self.job_id,
            'action_id': self.action_id,
            'action_name': self.action_name,
            'module': self.module,
            'risk_class': self.risk_class,
            'status': self.status,
            'queued_at': self.queued_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'output': self.output,
            'error': self.error,
            'return_code': self.return_code,
            'duration_ms': self.duration_ms,
            'needs_reboot': self.needs_reboot,
            'progress': self.progress,
        }


class JobRunner:
    """
    Manages background job execution.

    Provides:
    - Thread pool for concurrent execution
    - Job lifecycle management
    - Module-level locking via PolicyEngine
    - Full audit trail via persistence layer
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS,
                                            thread_name_prefix='cleancpu-job')
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, action: ActionDef, handler: Callable,
               session_id: str, hostname: str = '', username: str = '',
               is_admin: bool = False, params: Optional[dict] = None,
               confirmation_token: Optional[str] = None) -> dict:
        """
        Submit an action for execution.

        For short actions (not is_long_running), executes synchronously.
        For long-running actions, submits to background thread pool.

        Returns:
            dict with job_id, status, and result (if synchronous)
        """
        # Validate against policy
        validation = policy.validate_action(action, is_admin, confirmation_token)
        if not validation.get('allowed', False):
            return {
                'status': 'rejected',
                'reason': validation.get('reason', 'Action not allowed'),
                'violation_type': validation.get('violation_type', 'policy_violation'),
            }

        # Check if confirmation is still needed
        if validation.get('needs_confirmation', False):
            return {
                'status': 'needs_confirmation',
                'confirm_message': validation.get('confirm_message', ''),
                'action_id': action.action_id,
                'risk_class': action.risk_class.value,
                'needs_restore_point': validation.get('needs_restore_point', False),
                'needs_reboot': validation.get('needs_reboot', False),
                'warnings': validation.get('warnings', []),
            }

        # Create job
        job = Job(action, session_id, hostname, username, is_admin, handler, params)

        # Persist job creation
        JobStore.create(
            job_id=job.job_id, session_id=session_id,
            action_id=action.action_id, action_name=action.name,
            module=action.module, risk_class=action.risk_class.value,
            hostname=hostname, username=username, is_admin=is_admin,
            parameters=params,
        )

        with self._lock:
            self._jobs[job.job_id] = job

        if action.is_long_running:
            # Background execution
            self._executor.submit(self._execute_job, job)
            return {
                'status': 'submitted',
                'job_id': job.job_id,
                'action_name': action.name,
                'message': f'Job {job.job_id} submitted for background execution.',
                'warnings': validation.get('warnings', []),
            }
        else:
            # Synchronous execution
            self._execute_job(job)
            result = job.to_dict()
            # For synchronous jobs, return the full result directly
            result['status'] = job.status
            return result

    def _execute_job(self, job: Job):
        """Execute a job (runs in background thread for long-running jobs)."""
        # Acquire module lock
        if not policy.acquire_lock(job.module, job.job_id):
            job.status = 'failed'
            job.error = f'Module "{job.module}" is locked by another job.'
            job.completed_at = datetime.now().isoformat()
            JobStore.update_completed(job.job_id, 'failed', error_message=job.error)
            AuditStore.log(
                session_id=job.session_id, module=job.module,
                action=job.action_name, status='failed',
                job_id=job.job_id, action_id=job.action_id,
                risk_class=job.risk_class, hostname=job.hostname,
                username=job.username, is_admin=job.is_admin,
                stderr_preview=job.error,
            )
            return

        # Lock is held — from this point on the finally MUST release it,
        # even if BaseException (SystemExit, KeyboardInterrupt) propagates.
        start_time = time.time()
        try:
            # Mark as running
            job.status = 'running'
            job.started_at = datetime.now().isoformat()
            JobStore.update_started(job.job_id)
            logger.info(f"Job {job.job_id} started: {job.action_name}")

            # Execute the handler
            if job.params:
                result = job.handler(**job.params)
            else:
                result = job.handler()

            duration_ms = int((time.time() - start_time) * 1000)

            # Dispatch result processing based on result type
            if isinstance(result, dict):
                _apply_dict_result(job, result, duration_ms)
            elif hasattr(result, 'to_dict'):
                _apply_command_result(job, result, duration_ms)
            else:
                _apply_generic_result(job, result, duration_ms)

            job.completed_at = datetime.now().isoformat()

            # Persist result
            JobStore.update_completed(
                job.job_id, job.status,
                stdout=job.output, stderr=job.error,
                return_code=job.return_code,
                duration_ms=job.duration_ms,
                needs_reboot=job.needs_reboot,
            )

            # Audit trail
            AuditStore.log(
                session_id=job.session_id, module=job.module,
                action=job.action_name, status=job.status,
                job_id=job.job_id, action_id=job.action_id,
                risk_class=job.risk_class, hostname=job.hostname,
                username=job.username, is_admin=job.is_admin,
                return_code=job.return_code,
                stdout_preview=job.output[:500] if job.output else '',
                stderr_preview=job.error[:500] if job.error else '',
                duration_ms=job.duration_ms,
            )

            logger.info(f"Job {job.job_id} {job.status}: {job.action_name} ({job.duration_ms}ms)")

        except Exception as e:
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now().isoformat()
            job.duration_ms = int((time.time() - start_time) * 1000)

            JobStore.update_completed(job.job_id, 'failed', error_message=str(e))
            AuditStore.log(
                session_id=job.session_id, module=job.module,
                action=job.action_name, status='failed',
                job_id=job.job_id, action_id=job.action_id,
                risk_class=job.risk_class, hostname=job.hostname,
                username=job.username, is_admin=job.is_admin,
                stderr_preview=str(e)[:500],
            )
            logger.error(f"Job {job.job_id} failed: {e}")

        finally:
            # Defensive: even if release_lock raises (it shouldn't), swallow
            # the error so the worker thread exits cleanly instead of dying
            # with the lock still held.
            try:
                policy.release_lock(job.module)
            except Exception:
                logger.exception(
                    f"Unexpected error releasing lock for module {job.module!r} "
                    f"(job {job.job_id})"
                )

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status. Checks in-memory first, falls back to DB."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job.to_dict()

        # Fall back to DB for completed jobs that were cleaned from memory
        db_job = JobStore.get(job_id)
        return db_job

    def list_active(self) -> list[dict]:
        """List all active (queued/running) jobs."""
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()
                    if j.status in ('queued', 'running')]

    def list_recent(self, session_id: str, limit: int = 50) -> list[dict]:
        """List recent jobs for a session."""
        return JobStore.list_by_session(session_id, limit)

    def cancel_job(self, job_id: str) -> dict:
        """
        Request cancellation of a job.
        For queued jobs: immediately cancel.
        For running jobs: set cancel_requested flag and attempt process kill.
        """
        with self._lock:
            job = self._jobs.get(job_id)

        if not job:
            # Try DB
            db_job = JobStore.get(job_id)
            if db_job and db_job.get('status') in ('queued', 'running'):
                JobStore.cancel(job_id)
                return {'status': 'cancelled', 'job_id': job_id, 'message': 'Job cancelled in DB.'}
            return {'status': 'error', 'error': 'Job not found or already completed.'}

        if job.status == 'queued':
            job.status = 'cancelled'
            job.completed_at = datetime.now().isoformat()
            JobStore.cancel(job_id)
            logger.info(f"Job {job_id} cancelled (was queued)")
            return {'status': 'cancelled', 'job_id': job_id, 'message': 'Queued job cancelled.'}

        if job.status == 'running':
            job.cancel_requested = True
            # Try to kill the process tree if we have a reference
            if job.process:
                try:
                    import subprocess
                    import sys
                    if sys.platform == 'win32':
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(job.process.pid)],
                            capture_output=True, timeout=10,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                        )
                    else:
                        job.process.kill()
                except Exception as e:
                    logger.warning(f"Could not kill process for job {job_id}: {e}")

            logger.info(f"Cancel requested for running job {job_id}")
            return {
                'status': 'cancel_requested',
                'job_id': job_id,
                'message': 'Cancellation requested. The process may still be running briefly.',
            }

        return {'status': 'error', 'error': f'Job is already {job.status}, cannot cancel.'}

    def cleanup_completed(self, max_age_seconds: int = 3600):
        """Remove completed jobs from in-memory cache (they persist in DB)."""
        with self._lock:
            to_remove = []
            now = datetime.now()
            for job_id, job in self._jobs.items():
                if job.status in ('completed', 'failed', 'cancelled', 'partial_success'):
                    if job.completed_at:
                        completed = datetime.fromisoformat(job.completed_at)
                        if (now - completed).total_seconds() > max_age_seconds:
                            to_remove.append(job_id)
            for job_id in to_remove:
                del self._jobs[job_id]

    def shutdown(self):
        """Gracefully shutdown the thread pool."""
        self._executor.shutdown(wait=True, cancel_futures=False)


# Global job runner instance
job_runner = JobRunner()
