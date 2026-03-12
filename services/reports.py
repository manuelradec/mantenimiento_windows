"""
Logging and reporting module.

Handles: log management, report generation, export functionality.
"""
import os
import json
import logging
from datetime import datetime

from config import Config

logger = logging.getLogger('maintenance.reports')


class MaintenanceLog:
    """Centralized maintenance log manager."""

    def __init__(self):
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(
            Config.LOG_DIR, f'maintenance_{self.session_id}.log'
        )
        self.entries = []
        self._setup_file_logger()

    def _setup_file_logger(self):
        """Set up file-based logging."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        handler = logging.FileHandler(self.log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        root_logger = logging.getLogger('maintenance')
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    def add_entry(self, module, action, status, result='', error='', details=None):
        """Add an entry to the maintenance log."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'module': module,
            'action': action,
            'status': status,
            'result': result,
            'error': error,
            'details': details or {},
        }
        self.entries.append(entry)
        logger.info(f"[{module}] {action}: {status} - {result or error}")
        return entry

    def get_entries(self, module=None, status=None):
        """Get log entries, optionally filtered."""
        entries = self.entries
        if module:
            entries = [e for e in entries if e['module'] == module]
        if status:
            entries = [e for e in entries if e['status'] == status]
        return entries

    def get_summary(self):
        """Get a summary of all maintenance actions."""
        total = len(self.entries)
        by_status = {}
        by_module = {}
        for entry in self.entries:
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
        lines = [
            f"{'='*70}",
            f"  MAINTENANCE REPORT - {Config.APP_NAME} v{Config.APP_VERSION}",
            f"  Session: {self.session_id}",
            f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'='*70}",
            "",
        ]

        summary = self.get_summary()
        lines.append(f"SUMMARY: {summary['total_actions']} actions performed")
        for status, count in summary['by_status'].items():
            lines.append(f"  - {status}: {count}")
        lines.append("")
        lines.append(f"{'='*70}")
        lines.append("DETAILED LOG:")
        lines.append(f"{'='*70}")

        for entry in self.entries:
            lines.append(f"\n[{entry['timestamp']}] [{entry['module']}]")
            lines.append(f"  Action: {entry['action']}")
            lines.append(f"  Status: {entry['status']}")
            if entry['result']:
                lines.append(f"  Result: {entry['result'][:200]}")
            if entry['error']:
                lines.append(f"  Error: {entry['error'][:200]}")

        lines.append(f"\n{'='*70}")
        lines.append("END OF REPORT")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return filepath

    def export_html(self, filepath=None):
        """Export the log as an HTML report."""
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
                'not_applicable': 'status-na',
            }.get(entry['status'], '')

            rows += f'''<tr>
                <td>{entry['timestamp'][:19]}</td>
                <td>{entry['module']}</td>
                <td>{entry['action']}</td>
                <td class="{status_class}">{entry['status']}</td>
                <td>{entry['result'][:100] if entry['result'] else entry['error'][:100] if entry['error'] else '-'}</td>
            </tr>'''

        html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Maintenance Report - {self.session_id}</title>
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
    <h1>Maintenance Report</h1>
    <div class="summary">
        <p><strong>Session:</strong> {self.session_id}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Actions:</strong> {summary['total_actions']}</p>
        <p><strong>Results:</strong>
            {' | '.join(f'{status}: {count}' for status, count in summary['by_status'].items())}
        </p>
    </div>
    <table>
        <thead>
            <tr><th>Time</th><th>Module</th><th>Action</th><th>Status</th><th>Details</th></tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
</body>
</html>'''

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        return filepath


# Global instance (initialized when app starts)
maintenance_log = None


def get_log():
    """Get or create the global maintenance log."""
    global maintenance_log
    if maintenance_log is None:
        maintenance_log = MaintenanceLog()
    return maintenance_log


def reset_log():
    """Reset the global maintenance log (new session)."""
    global maintenance_log
    maintenance_log = MaintenanceLog()
    return maintenance_log
