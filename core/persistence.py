"""
SQLite Persistence Layer - Structured local storage for jobs, audit trail, and reports.

Tables:
- sessions: Application sessions
- jobs: Background job records with full lifecycle
- audit_log: Every action executed with structured fields
"""
import os
import json
import sqlite3
import logging
import threading
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

from config import Config

logger = logging.getLogger('cleancpu.persistence')

DB_FILENAME = 'cleancpu.db'


def _get_db_path() -> str:
    """Get the path to the SQLite database."""
    db_dir = Config.LOG_DIR
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, DB_FILENAME)


# Thread-local storage for connections
_local = threading.local()


@contextmanager
def get_db():
    """Get a thread-local database connection with auto-commit context."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        db_path = _get_db_path()
        _local.conn = sqlite3.connect(db_path, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield _local.conn
        _local.conn.commit()
    except Exception:
        _local.conn.rollback()
        raise


def init_db():
    """Initialize the database schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                hostname TEXT,
                username TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                os_info TEXT,
                app_version TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                action_name TEXT NOT NULL,
                module TEXT NOT NULL,
                risk_class TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                queued_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                duration_ms INTEGER,
                hostname TEXT,
                username TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                command TEXT,
                return_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                needs_reboot INTEGER NOT NULL DEFAULT 0,
                rollback_info TEXT,
                parameters_json TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                job_id TEXT,
                module TEXT NOT NULL,
                action TEXT NOT NULL,
                action_id TEXT,
                risk_class TEXT,
                status TEXT NOT NULL,
                hostname TEXT,
                username TEXT,
                is_admin INTEGER,
                command TEXT,
                return_code INTEGER,
                stdout_preview TEXT,
                stderr_preview TEXT,
                duration_ms INTEGER,
                details_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_module ON audit_log(module);
        """)
    logger.info(f"Database initialized at {_get_db_path()}")


class SessionStore:
    """Manages session records."""

    @staticmethod
    def create(session_id: str, hostname: str = '', username: str = '',
               is_admin: bool = False, os_info: str = '', app_version: str = ''):
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions "
                "(session_id, started_at, hostname, username, is_admin, os_info, app_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, datetime.now().isoformat(), hostname, username,
                 int(is_admin), os_info, app_version)
            )

    @staticmethod
    def close(session_id: str):
        with get_db() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
                (datetime.now().isoformat(), session_id)
            )

    @staticmethod
    def get(session_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None


class JobStore:
    """Manages job records."""

    @staticmethod
    def create(job_id: str, session_id: str, action_id: str, action_name: str,
               module: str, risk_class: str, hostname: str = '', username: str = '',
               is_admin: bool = False, parameters: Optional[dict] = None):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO jobs "
                "(job_id, session_id, action_id, action_name, module, risk_class, "
                "status, queued_at, hostname, username, is_admin, parameters_json) "
                "VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
                (job_id, session_id, action_id, action_name, module, risk_class,
                 datetime.now().isoformat(), hostname, username, int(is_admin),
                 json.dumps(parameters) if parameters else None)
            )

    @staticmethod
    def update_started(job_id: str, command: str = ''):
        with get_db() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, command = ? "
                "WHERE job_id = ?",
                (datetime.now().isoformat(), command, job_id)
            )

    @staticmethod
    def update_completed(job_id: str, status: str, stdout: str = '', stderr: str = '',
                         return_code: Optional[int] = None, duration_ms: int = 0,
                         error_message: str = '', needs_reboot: bool = False):
        with get_db() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, completed_at = ?, stdout = ?, stderr = ?, "
                "return_code = ?, duration_ms = ?, error_message = ?, needs_reboot = ? "
                "WHERE job_id = ?",
                (status, datetime.now().isoformat(), stdout, stderr,
                 return_code, duration_ms, error_message, int(needs_reboot), job_id)
            )

    @staticmethod
    def get(job_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_by_session(session_id: str, limit: int = 100) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE session_id = ? ORDER BY queued_at DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def list_active() -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('queued', 'running') "
                "ORDER BY queued_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def cancel(job_id: str):
        with get_db() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'cancelled', completed_at = ? "
                "WHERE job_id = ? AND status IN ('queued', 'running')",
                (datetime.now().isoformat(), job_id)
            )


class AuditStore:
    """Manages the audit log."""

    @staticmethod
    def log(session_id: str, module: str, action: str, status: str,
            job_id: str = '', action_id: str = '', risk_class: str = '',
            hostname: str = '', username: str = '', is_admin: bool = False,
            command: str = '', return_code: Optional[int] = None,
            stdout_preview: str = '', stderr_preview: str = '',
            duration_ms: int = 0, details: Optional[dict] = None):
        """Write an audit log entry."""
        with get_db() as conn:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, session_id, job_id, module, action, action_id, risk_class, "
                "status, hostname, username, is_admin, command, return_code, "
                "stdout_preview, stderr_preview, duration_ms, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), session_id, job_id, module, action,
                 action_id, risk_class, status, hostname, username, int(is_admin),
                 command, return_code,
                 stdout_preview[:500] if stdout_preview else '',
                 stderr_preview[:500] if stderr_preview else '',
                 duration_ms,
                 json.dumps(details) if details else None)
            )

    @staticmethod
    def get_entries(session_id: str, module: Optional[str] = None,
                    limit: int = 200) -> list[dict]:
        """Get audit log entries."""
        with get_db() as conn:
            if module:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE session_id = ? AND module = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (session_id, module, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE session_id = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_summary(session_id: str) -> dict:
        """Get audit summary for a session."""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE session_id = ?",
                (session_id,)
            ).fetchone()[0]

            by_status = {}
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM audit_log "
                "WHERE session_id = ? GROUP BY status",
                (session_id,)
            ).fetchall():
                by_status[row['status']] = row['cnt']

            by_module = {}
            for row in conn.execute(
                "SELECT module, COUNT(*) as cnt FROM audit_log "
                "WHERE session_id = ? GROUP BY module",
                (session_id,)
            ).fetchall():
                by_module[row['module']] = row['cnt']

            return {
                'session_id': session_id,
                'total_actions': total,
                'by_status': by_status,
                'by_module': by_module,
            }
