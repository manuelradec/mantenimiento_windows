"""
CleanCPU Production Server - Waitress-based local WSGI server.

This is the production entrypoint for the packaged executable.
Uses Waitress instead of Flask's development server for:
- Proper WSGI compliance
- Thread safety
- Graceful shutdown
- Production-grade request handling

Usage:
    python server.py              # Production mode (Waitress)
    python server.py --dev        # Development mode (Flask debug server)
"""
import os
import sys
import signal
import logging
import webbrowser
import threading
import argparse
from datetime import datetime

from app import create_app
from config import Config
from core.persistence import init_db, SessionStore
from core.job_runner import job_runner
from services.permissions import get_elevation_info


def _get_session_id() -> str:
    """Generate a unique session identifier."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _get_hostname() -> str:
    """Get the machine hostname."""
    import socket
    try:
        return socket.gethostname()
    except Exception:
        return 'unknown'


def _get_username() -> str:
    """Get the current username."""
    try:
        return os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))
    except Exception:
        return 'unknown'


def open_browser(port: int, delay: float = 1.5):
    """Open the default browser after a short delay."""
    def _open():
        import time
        time.sleep(delay)
        webbrowser.open(f'http://127.0.0.1:{port}')
    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def run_production(app, port: int):
    """Run the application using Waitress (production WSGI server)."""
    try:
        from waitress import serve
    except ImportError:
        print("\n[ERROR] Waitress is not installed.")
        print("Install it with: pip install waitress")
        print("Falling back to Flask development server...\n")
        run_development(app, port)
        return

    print(f"\n{'='*60}")
    print(f"  CleanCPU v{Config.APP_VERSION} - Production Mode")
    print(f"  Server: Waitress (WSGI)")
    print(f"  URL: http://127.0.0.1:{port}")
    print(f"  Admin: {get_elevation_info()['is_admin']}")
    print(f"  Logs: {Config.LOG_DIR}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    open_browser(port)

    serve(
        app,
        host='127.0.0.1',
        port=port,
        threads=6,
        channel_timeout=120,
        cleanup_interval=30,
        url_scheme='http',
        ident='CleanCPU',
        # Only listen on localhost
        _quiet=False,
    )


def run_development(app, port: int):
    """Run the application using Flask's development server."""
    print(f"\n{'='*60}")
    print(f"  CleanCPU v{Config.APP_VERSION} - Development Mode")
    print(f"  Server: Flask (development)")
    print(f"  URL: http://127.0.0.1:{port}")
    print(f"  Admin: {get_elevation_info()['is_admin']}")
    print(f"  Logs: {Config.LOG_DIR}")
    print(f"{'='*60}\n")

    open_browser(port)

    app.run(
        host='127.0.0.1',
        port=port,
        debug=True,
        threaded=True,
        use_reloader=False,
    )


def main():
    """Main entry point with production/development mode selection."""
    parser = argparse.ArgumentParser(description='CleanCPU Maintenance Server')
    parser.add_argument('--dev', action='store_true',
                        help='Run in development mode (Flask debug server)')
    parser.add_argument('--port', type=int, default=None,
                        help='Override server port')
    parser.add_argument('--no-browser', action='store_true',
                        help='Do not open browser automatically')
    args = parser.parse_args()

    port = args.port or Config.PORT

    # Set up logging
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('waitress').setLevel(logging.INFO)

    # Initialize database
    init_db()

    # Create session record
    session_id = _get_session_id()
    elevation = get_elevation_info()
    hostname = _get_hostname()
    username = _get_username()

    SessionStore.create(
        session_id=session_id,
        hostname=hostname,
        username=username,
        is_admin=elevation['is_admin'],
        os_info=f"{sys.platform}",
        app_version=Config.APP_VERSION,
    )

    # Create app and store session info
    app = create_app()
    app.config['SESSION_ID'] = session_id
    app.config['HOSTNAME'] = hostname
    app.config['USERNAME'] = username

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        print("\n[CleanCPU] Shutting down...")
        SessionStore.close(session_id)
        job_runner.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    if args.no_browser:
        # Patch out browser opening
        global open_browser
        open_browser = lambda port, delay=0: None

    if args.dev:
        run_development(app, port)
    else:
        run_production(app, port)


if __name__ == '__main__':
    main()
