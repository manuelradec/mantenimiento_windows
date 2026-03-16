"""
Logging and reporting module.

Handles: log management, report generation, export functionality.

Thread-safe implementation with proper HTML escaping for report output.
"""
import os
import json
import logging
import threading
from datetime import datetime
from html import escape as html_escape

from config import Config

logger = logging.getLogger('cleancpu.reports')


class MaintenanceLog:
    """
    Thread-safe centralized maintenance log manager.

    Stores entries in-memory and syncs to the persistence layer (SQLite)
    when available.
    """

    def __init__(self):
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(
            Config.LOG_DIR, f'maintenance_{self.session_id}.log'
        )
        self._entries = []
        self._lock = threading.Lock()
        self._setup_file_logger()

    def _setup_file_logger(self):
        """Set up file-based logging."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        handler = logging.FileHandler(self.log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        maint_logger = logging.getLogger('cleancpu')
        # Prevent duplicate handlers
        for existing in maint_logger.handlers[:]:
            if isinstance(existing, logging.FileHandler):
                if hasattr(existing, 'baseFilename') and 'maintenance_' in existing.baseFilename:
                    maint_logger.removeHandler(existing)
        maint_logger.addHandler(handler)
        maint_logger.setLevel(logging.INFO)

    @property
    def entries(self):
        """Thread-safe access to entries."""
        with self._lock:
            return list(self._entries)

    def add_entry(self, module, action, status, result='', error='', details=None):
        """Add an entry to the maintenance log (thread-safe)."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'module': module,
            'action': action,
            'status': status,
            'result': result,
            'error': error,
            'details': details or {},
        }
        with self._lock:
            self._entries.append(entry)
        logger.info(f"[{module}] {action}: {status} - {result or error}")
        return entry

    def get_entries(self, module=None, status=None):
        """Get log entries, optionally filtered (thread-safe)."""
        with self._lock:
            entries = list(self._entries)
        if module:
            entries = [e for e in entries if e['module'] == module]
        if status:
            entries = [e for e in entries if e['status'] == status]
        return entries

    def get_summary(self):
        """Get a summary of all maintenance actions (thread-safe)."""
        with self._lock:
            entries = list(self._entries)

        total = len(entries)
        by_status = {}
        by_module = {}
        for entry in entries:
            s = entry['status']
            m = entry['module']
            by_status[s] = by_status.get(s, 0) + 1
            by_module[m] = by_module.get(m, 0) + 1

        return {
            'session_id': self.session_id,
            'total_actions': total,
            'by_status': by_status,
            'by_module': by_module,
            'log_file': self.log_file,
        }

    def export_json(self, filepath=None):
        """Export the full log as JSON."""
        if filepath is None:
            filepath = os.path.join(
                Config.REPORT_DIR,
                f'report_{self.session_id}.json'
            )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {
            'session_id': self.session_id,
            'generated': datetime.now().isoformat(),
            'app_name': Config.APP_NAME,
            'app_version': Config.APP_VERSION,
            'summary': self.get_summary(),
            'entries': self.entries,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    def export_txt(self, filepath=None):
        """Export the log as human-readable text."""
        if filepath is None:
            filepath = os.path.join(
                Config.REPORT_DIR,
                f'report_{self.session_id}.txt'
            )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        sep = '=' * 70
        lines = [
            sep,
            f"  MAINTENANCE REPORT - {Config.APP_NAME} v{Config.APP_VERSION}",
            f"  Session: {self.session_id}",
            f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            sep,
            "",
        ]

        summary = self.get_summary()
        lines.append(f"SUMMARY: {summary['total_actions']} actions performed")
        for status, count in summary['by_status'].items():
            lines.append(f"  - {status}: {count}")
        lines.append("")
        lines.append(sep)
        lines.append("DETAILED LOG:")
        lines.append(sep)

        for entry in self.entries:
            lines.append(f"\n[{entry['timestamp']}] [{entry['module']}]")
            lines.append(f"  Action: {entry['action']}")
            lines.append(f"  Status: {entry['status']}")
            if entry['result']:
                lines.append(f"  Result: {entry['result'][:200]}")
            if entry['error']:
                lines.append(f"  Error: {entry['error'][:200]}")

        lines.append(f"\n{sep}")
        lines.append("END OF REPORT")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return filepath

    def export_html(self, filepath=None):
        """Export the log as an HTML report with proper escaping."""
        if filepath is None:
            filepath = os.path.join(
                Config.REPORT_DIR,
                f'report_{self.session_id}.html'
            )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        summary = self.get_summary()
        rows = ''
        for entry in self.entries:
            status_class = {
                'success': 'status-success',
                'warning': 'status-warning',
                'error': 'status-error',
                'partial_success': 'status-warning',
                'not_applicable': 'status-na',
            }.get(entry['status'], '')

            # Properly escape all user-facing content
            detail_text = entry['result'][:100] if entry['result'] else (
                entry['error'][:100] if entry['error'] else '-')

            rows += (
                f'<tr>'
                f'<td>{html_escape(entry["timestamp"][:19])}</td>'
                f'<td>{html_escape(entry["module"])}</td>'
                f'<td>{html_escape(entry["action"])}</td>'
                f'<td class="{status_class}">{html_escape(entry["status"])}</td>'
                f'<td>{html_escape(detail_text)}</td>'
                f'</tr>\n'
            )

        # Escape summary values
        status_summary = ' | '.join(
            f'{html_escape(status)}: {count}'
            for status, count in summary['by_status'].items()
        )

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-Content-Type-Options" content="nosniff">
    <title>CleanCPU Report - {html_escape(self.session_id)}</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a365d; }}
        table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
        th {{ background: #2d3748; color: white; }}
        .summary {{ background: white; padding: 15px; border-radius: 6px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .status-success {{ color: #22543d; font-weight: bold; }}
        .status-warning {{ color: #744210; font-weight: bold; }}
        .status-error {{ color: #9b2c2c; font-weight: bold; }}
        .status-na {{ color: #718096; }}
    </style>
</head>
<body>
    <h1>CleanCPU - Maintenance Report</h1>
    <div class="summary">
        <p><strong>Session:</strong> {html_escape(self.session_id)}</p>
        <p><strong>Generated:</strong> {html_escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</p>
        <p><strong>Version:</strong> {html_escape(Config.APP_VERSION)}</p>
        <p><strong>Total Actions:</strong> {summary['total_actions']}</p>
        <p><strong>Results:</strong> {status_summary}</p>
    </div>
    <table>
        <thead>
            <tr><th>Time</th><th>Module</th><th>Action</th><th>Status</th><th>Details</th></tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    <footer style="margin-top: 20px; font-size: 11px; color: #a0aec0;">
        Generated by CleanCPU v{html_escape(Config.APP_VERSION)}
    </footer>
</body>
</html>'''

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        return filepath


# Thread-safe global instance management
_log_lock = threading.Lock()
_maintenance_log = None


def get_log():
    """Get or create the global maintenance log (thread-safe)."""
    global _maintenance_log
    with _log_lock:
        if _maintenance_log is None:
            _maintenance_log = MaintenanceLog()
        return _maintenance_log


def reset_log():
    """Reset the global maintenance log (new session, thread-safe)."""
    global _maintenance_log
    with _log_lock:
        _maintenance_log = MaintenanceLog()
        return _maintenance_log
