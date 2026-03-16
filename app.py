"""
CleanCPU - Professional Windows Maintenance Tool
Flask-based local web application for Windows 10/11 logical maintenance.

This module creates and configures the Flask application.
For production execution, use server.py (Waitress).
For development, use server.py --dev.
"""
import os
import sys
import logging
import webbrowser
import threading

from flask import Flask, jsonify, request

from config import Config, get_base_path
from routes import register_blueprints
from services.permissions import get_elevation_info
from core.security import init_security
from core.persistence import init_db
from core.policy_engine import policy
from core.action_registry import registry, OperationMode
from core.job_runner import job_runner


def create_app():
    """Application factory - creates and configures the Flask app."""
    # Handle PyInstaller paths
    base_path = get_base_path()
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')

    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder,
    )
    app.config.from_object(Config)

    # Initialize security middleware (CSRF, Origin validation, headers)
    init_security(app)

    # Initialize database
    init_db()

    # Make elevation info and config available to all templates
    @app.context_processor
    def inject_globals():
        return {
            'elevation': get_elevation_info(),
            'config': {
                'APP_NAME': Config.APP_NAME,
                'APP_VERSION': Config.APP_VERSION,
            },
            'policy_mode': policy.mode.value,
        }

    # Register all route blueprints
    register_blueprints(app)

    # Register core API routes (jobs, policy)
    _register_core_routes(app)

    # Initialize logging
    _setup_logging(app)

    return app


def _register_core_routes(app):
    """Register core API endpoints for jobs, policy, action registry, and system info."""

    @app.route('/api/system-overview')
    def api_system_overview():
        from services.system_info import get_system_overview
        return jsonify(get_system_overview())

    @app.route('/api/elevation')
    def api_elevation():
        return jsonify(get_elevation_info())

    # === Job Management ===

    @app.route('/api/jobs/<job_id>')
    def api_get_job(job_id):
        """Poll job status."""
        job = job_runner.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)

    @app.route('/api/jobs')
    def api_list_jobs():
        """List active jobs."""
        active = job_runner.list_active()
        return jsonify({'jobs': active})

    @app.route('/api/jobs/recent')
    def api_recent_jobs():
        """List recent jobs for current session."""
        session_id = app.config.get('SESSION_ID', 'unknown')
        jobs = job_runner.list_recent(session_id, limit=50)
        return jsonify({'jobs': jobs})

    @app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
    def api_cancel_job(job_id):
        """Request cancellation of a running/queued job."""
        result = job_runner.cancel_job(job_id)
        return jsonify(result)

    # === Policy Engine ===

    @app.route('/api/policy/status')
    def api_policy_status():
        """Get current policy status."""
        return jsonify(policy.get_status())

    @app.route('/api/policy/mode', methods=['POST'])
    def api_set_mode():
        """Change the operation mode."""
        data = request.get_json(silent=True) or {}
        mode_str = data.get('mode', '')
        try:
            mode = OperationMode(mode_str)
        except ValueError:
            valid = [m.value for m in OperationMode]
            return jsonify({'error': f'Invalid mode. Valid: {valid}'}), 400

        from core.governance import write_jsonl_event
        write_jsonl_event({
            'event': 'mode_change',
            'old_mode': policy.mode.value,
            'new_mode': mode_str,
        })
        policy.set_mode(mode)
        return jsonify(policy.get_status())

    @app.route('/api/policy/confirm', methods=['POST'])
    def api_confirm_action():
        """Register a confirmation token for a pending action."""
        data = request.get_json(silent=True) or {}
        token = data.get('token', '')
        if not token:
            return jsonify({'error': 'Missing confirmation token'}), 400
        policy.add_confirmation(token)
        return jsonify({'status': 'confirmed', 'token': token})

    # === Action Registry ===

    @app.route('/api/actions')
    def api_list_actions():
        """List all registered actions with metadata."""
        return jsonify(registry.to_dict())

    @app.route('/api/actions/allowed')
    def api_allowed_actions():
        """List actions allowed in current mode."""
        allowed = registry.list_allowed(policy.mode)
        return jsonify({a.action_id: a.to_dict() for a in allowed})


def _setup_logging(app):
    """Configure application logging."""
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    console_handler.setLevel(logging.INFO)

    # File handler
    log_file = os.path.join(Config.LOG_DIR, 'app.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.DEBUG)

    # Root logger
    root_logger = logging.getLogger()
    # Avoid adding duplicate handlers
    if not root_logger.handlers:
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    # Suppress noisy Flask/Werkzeug logs
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    app.logger.info(f"{Config.APP_NAME} v{Config.APP_VERSION} starting...")
    app.logger.info(f"Log directory: {Config.LOG_DIR}")
    app.logger.info(f"Admin: {get_elevation_info()['is_admin']}")


def open_browser(port):
    """Open the default browser after a short delay."""
    def _open():
        import time
        time.sleep(1.5)
        webbrowser.open(f'http://127.0.0.1:{port}')
    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def main():
    """
    Legacy entry point for development.
    For production, use server.py instead.
    """
    app = create_app()
    port = Config.PORT

    print(f"\n{'='*60}")
    print(f"  {Config.APP_NAME} v{Config.APP_VERSION}")
    print(f"  [DEV MODE] Running at: http://127.0.0.1:{port}")
    print("  For production, use: python server.py")
    print(f"  Admin: {get_elevation_info()['is_admin']}")
    print(f"  Logs: {Config.LOG_DIR}")
    print(f"{'='*60}\n")

    open_browser(port)

    app.run(
        host=Config.HOST,
        port=port,
        debug=Config.DEBUG,
        threaded=Config.THREADED,
        use_reloader=False,
    )


if __name__ == '__main__':
    main()
