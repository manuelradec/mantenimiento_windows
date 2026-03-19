"""Log viewer routes."""
import os
import logging
from flask import Blueprint, render_template, jsonify, request, send_file

from config import Config

logs_bp = Blueprint('logs', __name__)
logger = logging.getLogger('cleancpu.logs')


@logs_bp.route('/')
def index():
    return render_template('logs.html')


@logs_bp.route('/api/entries')
def api_log_entries():
    """Return recent log entries as JSON for the in-app viewer."""
    level_filter = request.args.get('level', 'all').upper()
    search = request.args.get('search', '').strip()
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 500))

    log_file = os.path.join(Config.LOG_DIR, 'app.log')
    entries = []

    try:
        if not os.path.exists(log_file):
            return jsonify({'entries': [], 'total': 0})

        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        # Parse log lines: "2026-03-16 10:30:00,123 [INFO] module: message"
        for line in lines:
            line = line.rstrip('\n')
            if not line:
                continue

            entry = _parse_log_line(line)
            if not entry:
                continue

            # Apply level filter
            if level_filter != 'ALL' and entry['level'] != level_filter:
                continue

            # Apply search filter
            if search and search.lower() not in line.lower():
                continue

            entries.append(entry)

        total = len(entries)
        # Return most recent entries first
        entries.reverse()
        entries = entries[offset:offset + limit]

        return jsonify({'entries': entries, 'total': total})
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return jsonify({'entries': [], 'total': 0, 'error': str(e)})


@logs_bp.route('/api/download')
def api_download_log():
    """Download the full log file."""
    log_file = os.path.join(Config.LOG_DIR, 'app.log')
    if not os.path.exists(log_file):
        return jsonify({'error': 'No log file found'}), 404
    return send_file(log_file, as_attachment=True, download_name='cleancpu.log')


def _parse_log_line(line):
    """Parse a log line into structured components."""
    # Format: "2026-03-16 10:30:00,123 [INFO] module.name: message text"
    try:
        # Find the level bracket
        bracket_start = line.find('[')
        bracket_end = line.find(']', bracket_start)
        if bracket_start < 0 or bracket_end < 0:
            return None

        timestamp = line[:bracket_start].strip()
        level = line[bracket_start + 1:bracket_end]

        rest = line[bracket_end + 1:].strip()
        colon_pos = rest.find(':')
        if colon_pos > 0:
            module = rest[:colon_pos].strip()
            message = rest[colon_pos + 1:].strip()
        else:
            module = ''
            message = rest

        return {
            'timestamp': timestamp,
            'level': level,
            'module': module,
            'message': message,
        }
    except Exception:
        return None
