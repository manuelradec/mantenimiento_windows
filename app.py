"""
Mantenimiento Windows - Professional Windows Maintenance Tool
Flask-based local web application for Windows 10/11 logical maintenance.

This is the main entrypoint. It initializes Flask, registers blueprints,
configures logging, and starts the local server.
"""
import os
import sys
import logging
import webbrowser
import threading

from flask import Flask

from config import Config, get_base_path
from routes import register_blueprints
from services.permissions import get_elevation_info
from services.reports import get_log


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

    # Make elevation info available to all templates
    @app.context_processor
    def inject_globals():
        return {
            'elevation': get_elevation_info(),
            'config': {
                'APP_NAME': Config.APP_NAME,
                'APP_VERSION': Config.APP_VERSION,
            },
        }

    # Register all route blueprints
    register_blueprints(app)

    # Initialize logging
    _setup_logging(app)

    # Initialize the maintenance log for this session
    get_log()

    return app


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
    """Main entry point."""
    app = create_app()
    port = Config.PORT

    print(f"\n{'='*60}")
    print(f"  {Config.APP_NAME} v{Config.APP_VERSION}")
    print(f"  Running at: http://127.0.0.1:{port}")
    print(f"  Admin: {get_elevation_info()['is_admin']}")
    print(f"  Logs: {Config.LOG_DIR}")
    print(f"{'='*60}\n")

    # Open browser automatically
    open_browser(port)

    # Run Flask (local only, no external access)
    app.run(
        host=Config.HOST,
        port=port,
        debug=Config.DEBUG,
        threaded=Config.THREADED,
        use_reloader=False,  # Important for PyInstaller compatibility
    )


if __name__ == '__main__':
    main()
